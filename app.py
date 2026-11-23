"""Editor do Jornal do RH · Léah Estética (Streamlit).

Rodar local:   streamlit run app.py
Online:        Streamlit Community Cloud (veja README.md)
"""
import copy
import hmac
import os
import re
import time
from datetime import date, datetime

import pandas as pd
import streamlit as st

import core

st.set_page_config(page_title="Editor do RH · Léah", page_icon="📰", layout="wide")


# ------------------------------------------------------------ configuração
def seg(nome, padrao=None):
    """Lê de st.secrets e, se não houver, de variável de ambiente."""
    try:
        if nome in st.secrets:
            return st.secrets[nome]
    except Exception:
        pass
    return os.environ.get(nome, padrao)


SENHA = seg("APP_PASSWORD")
SITE_URL = (seg("SITE_URL", "") or "").rstrip("/")
GH_TOKEN, GH_REPO = seg("GITHUB_TOKEN"), seg("GITHUB_REPO")


@st.cache_resource
def get_github():
    if GH_TOKEN and GH_REPO:
        return core.GitHub(GH_TOKEN, GH_REPO, seg("GITHUB_BRANCH", "main"))
    return None


gh = get_github()

# ------------------------------------------------------------------ senha
if gh and not SENHA:
    st.error("Segurança: defina APP_PASSWORD nos secrets antes de usar o editor online.")
    st.stop()
if SENHA and not st.session_state.get("autenticado"):
    st.title("📰 Editor do RH · Léah")
    with st.form("login"):
        digitada = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if hmac.compare_digest(str(digitada), str(SENHA)):
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    st.stop()


# ------------------------------------------------------------------ estado
def carregar_dados():
    try:
        return core.carregar_remoto(gh)
    except Exception as e:  # sem internet / GitHub fora: usa a cópia local
        st.session_state["_msg"] = ("warning", f"Não consegui ler do GitHub ({e}). Usando a cópia local.")
        return core.carregar_local()


if "dados" not in st.session_state:
    st.session_state.dados = carregar_dados()
    st.session_state.fotos_novas = {}
    st.session_state.alterado = False
    st.session_state.cnt = {}


def marcar():
    st.session_state.alterado = True


def get_gem():
    if "gem" not in st.session_state:
        st.session_state.gem = core.Gemini(core.carregar_chaves(st.secrets if _tem_secrets() else None))
    return st.session_state.gem


def _tem_secrets():
    try:
        len(st.secrets)
        return True
    except Exception:
        return False


# ------------------------------------------------------------- seções
CULT = ["Nossa missão", "Nossa visão", "Nossos valores", "Nosso propósito", "Padrão de atendimento",
        "Comportamentos esperados", "Postura profissional", "Trabalho em equipe",
        "Responsabilidade e comprometimento", "Frase do mês"]
SEG = ["Mensagem permanente", "Como pedir ajuda", "Assédio eleitoral", "Conteúdo educativo", "PGR em resumo",
       "Por setor", "Seus direitos e deveres"]

AREAS = {
    "nov": dict(nome="📰 Manchete e novidades", linhas=20, subs=["Novidade"], foto=True, video=True,
                ctx="Manchete e novidades do jornal do RH da Léah",
                ex="Unidade Léah Estética de Joaçaba, abertura em 2022",
                ajuda="A **manchete** é escolhida sozinha: é a novidade mais recente que tem foto ou vídeo."),
    "com": dict(nome="📢 Comunicados do RH", linhas=8, subs=["Aviso importante", "Comunicado", "Lembrete"],
                data=True, imp=True, ctx="Comunicados do RH", ex="Funcionamento das unidades no feriado de Natal"),
    "trein": dict(nome="🎓 Treinamentos e desenvolvimento", linhas=6, subs=["Treinamento", "Capacitação", "Workshop"],
                  data=True, hora=True, local=True, link=True, quem=True,
                  ctx="Treinamentos e desenvolvimento", ex="Treinamento de atendimento ao cliente"),
    "evt": dict(nome="🎉 Eventos e confraternizações", linhas=6, subs=["Evento", "Confraternização"],
                data=True, hora=True, local=True, foto=True, ctx="Eventos e confraternizações",
                ex="Confraternização de fim de ano da equipe"),
    "desafio": dict(nome="🎯 Desafio do mês", linhas=5, subs=[], mes=True, ctx="Desafio do mês para a equipe",
                    ex="Desafio da Gratidão",
                    ajuda="Só existe **um desafio por mês**: salvar outro para o mesmo mês substitui o anterior."),
    "equipe": dict(nome="🎂 Aniversariantes e equipe"),
    "cal": dict(nome="📅 Calendário do RH"),
    "rec": dict(nome="🏅 Reconhecimentos", linhas=5, subs=["Destaque do mês", "Reconhecimento"], pessoa=True,
                foto=True, ctx="Reconhecimentos", ex="Destaque do mês: atendimento nota 10"),
    "cult": dict(nome="💜 Cultura Léah", linhas=6, subs=CULT, ctx="Cultura Léah", ex="Nossos valores"),
    "seg": dict(nome="🛡️ Ambiente de trabalho saudável", linhas=8, subs=SEG, ctx="Ambiente de trabalho saudável",
                ex="Como pedir ajuda ao RH"),
    "pol": dict(nome="📄 Políticas da Léah", linhas=6, subs=["Política"], link=True, ctx="Políticas da Léah",
                ex="Política de uso de uniforme"),
    "info": dict(nome="ℹ️ Como funciona na Léah", linhas=6, subs=["Informação"], ctx="Como funciona na Léah",
                 ex="Como solicitar folga"),
    "cargo": dict(nome="👥 Cargos e funções", linhas=6, subs=["Função"], ctx="Cargos e funções",
                  ex="Função de recepcionista"),
}
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


def init(chave, valor):
    if chave not in st.session_state:
        st.session_state[chave] = valor


# ----------------------------------------------------------------- IA
def gerar_cb(p, area):
    """Callback do botão 'Gerar com IA' (roda antes da tela ser redesenhada)."""
    cfg = AREAS[area]
    ss = st.session_state
    tema = (ss.get(f"{p}_tema") or "").strip()
    if not tema:
        ss["_msg"] = ("warning", "Escreva o tema antes de gerar com IA.")
        return
    try:
        r = get_gem().texto(tema, int(ss.get(f"{p}_lin") or cfg["linhas"]), cfg["ctx"],
                            (ss.get(f"{p}_extra") or "").strip())
    except core.GeminiError as e:
        ss["_msg"] = ("error", str(e))
        return
    ss[f"{p}_txt"] = r["texto"]
    if not (ss.get(f"{p}_tit") or "").strip():
        ss[f"{p}_tit"] = tema if area == "desafio" else (r["titulo"] or tema)
    ss["_msg"] = ("success", "Texto gerado! Revise e ajuste abaixo antes de salvar.")


def bloco_ia(p, area):
    cfg = AREAS[area]
    with st.container(border=True):
        st.markdown("**✨ Escrever com IA** (opcional)")
        c1, c2 = st.columns([4, 1])
        c1.text_input("Sobre o quê?", key=f"{p}_tema", placeholder=f"Ex.: {cfg['ex']}")
        c2.number_input("Máx. de linhas", 1, 30, cfg["linhas"], key=f"{p}_lin")
        st.text_area("Informações que a IA pode usar (datas, nomes, detalhes reais)", key=f"{p}_extra", height=70,
                     placeholder="Opcional. A IA não inventa nada além do que estiver aqui.")
        st.button("✨ Gerar com IA", key=f"{p}_gerar", on_click=gerar_cb, args=(p, area))
        n = len(core.carregar_chaves(st.secrets if _tem_secrets() else None))
        st.caption(f"{n} chave(s) do Gemini disponível(is); se uma falhar, troca para a próxima sozinho.")


# ---------------------------------------------------------- formulário
def campos(p, area, it):
    """Desenha os campos de um item. Retorna dict com os valores e o arquivo de foto (se houver)."""
    cfg = AREAS[area]
    v = {}
    if cfg["subs"]:
        subs = list(cfg["subs"])
        atual = it.get("sub") or subs[0]
        if atual not in subs:
            subs.append(atual)
        init(f"{p}_sub", atual)
        v["sub"] = st.selectbox("Etiqueta", subs, key=f"{p}_sub")
    init(f"{p}_tit", it.get("tit", ""))
    init(f"{p}_txt", it.get("txt", ""))
    v["tit"] = st.text_input("Título", key=f"{p}_tit")
    v["txt"] = st.text_area("Texto", key=f"{p}_txt", height=180)

    if cfg.get("mes"):
        hoje = date.today()
        opcoes = []
        for i in range(0, 13):
            m = (hoje.month - 1 + i) % 12
            a = hoje.year + (hoje.month - 1 + i) // 12
            opcoes.append(f"{a}-{m + 1:02d}")
        atual = it.get("mes") or opcoes[0]
        if atual not in opcoes:
            opcoes.insert(0, atual)
        init(f"{p}_mes", atual)
        v["mes"] = st.selectbox("Mês do desafio", opcoes, key=f"{p}_mes",
                                format_func=lambda x: f"{MESES[int(x[5:]) - 1].capitalize()} de {x[:4]}")
    if cfg.get("data"):
        init(f"{p}_tem", bool(it.get("data")))
        init(f"{p}_data", date.fromisoformat(it["data"]) if it.get("data") else date.today())
        c1, c2 = st.columns([1, 2])
        tem = c1.checkbox("Tem data", key=f"{p}_tem")
        if tem:
            v["data"] = c2.date_input("Data", key=f"{p}_data", format="DD/MM/YYYY").isoformat()
    cols = st.columns(3)
    if cfg.get("hora"):
        init(f"{p}_hora", it.get("hora", ""))
        v["hora"] = cols[0].text_input("Horário", key=f"{p}_hora", placeholder="19h00")
    if cfg.get("local"):
        init(f"{p}_local", it.get("local", ""))
        v["local"] = cols[1].text_input("Local", key=f"{p}_local")
    if cfg.get("quem"):
        init(f"{p}_quem", it.get("quem", ""))
        v["quem"] = cols[2].text_input("Quem participa", key=f"{p}_quem")
    if cfg.get("pessoa"):
        init(f"{p}_pessoa", it.get("pessoa", ""))
        v["pessoa"] = st.text_input("Nome da pessoa reconhecida", key=f"{p}_pessoa")
    if cfg.get("link"):
        init(f"{p}_link", it.get("link", ""))
        v["link"] = st.text_input("Link (https://… ou politicas/arquivo.pdf)", key=f"{p}_link")
        parq = st.file_uploader(f"Ou envie o PDF (até {core.PDF_MAX_MB} MB)", type=["pdf"], key=f"{p}_pdfarq")
        if parq is not None and parq.size > core.PDF_MAX_MB * 1024 * 1024:
            st.error(f"PDF com {parq.size / 1048576:.0f} MB. O limite é {core.PDF_MAX_MB} MB: comprima o PDF e envie de novo.")
            parq = None
        v["_pdfarq"] = parq
        if parq is not None:
            st.caption("O PDF substitui o link acima ao salvar e publicar.")
    if cfg.get("video"):
        init(f"{p}_video", it.get("video", ""))
        v["video"] = st.text_input("Vídeo (link do YouTube ou .mp4)", key=f"{p}_video")
        if it.get("video") and str(it["video"]).startswith("videos/"):
            pend = st.session_state.fotos_novas.get(it["video"])
            if pend:
                st.video(pend)
                st.caption("Vídeo atual (ainda não publicado)")
            elif SITE_URL:
                st.video(f"{SITE_URL}/{it['video']}")
                st.caption("Vídeo atual")
        varq = st.file_uploader(f"Ou envie o arquivo de vídeo (MP4, até {core.VIDEO_MAX_MB} MB, ideal 30 s)",
                                type=["mp4", "webm"], key=f"{p}_videoarq")
        if varq is not None:
            if varq.size > core.VIDEO_MAX_MB * 1024 * 1024:
                st.error(f"Vídeo com {varq.size / 1048576:.0f} MB. O limite é {core.VIDEO_MAX_MB} MB: "
                         "reduza a qualidade/resolução (veja a dica abaixo) e envie de novo.")
                varq = None
            else:
                st.video(varq.getvalue())
        v["_videoarq"] = varq
        st.caption("Dica: vídeo de celular costuma ser pesado. Grave em 1080p ou use um compressor "
                   "(ex.: HandBrake, ou o próprio WhatsApp Web baixando o vídeo recebido).")
    if cfg.get("imp"):
        init(f"{p}_imp", bool(it.get("imp")))
        v["imp"] = st.checkbox("Marcar como “Você precisa saber!”", key=f"{p}_imp")

    todas = core.UNIDADES
    init(f"{p}_clis", it.get("clis") or todas)
    sel = st.multiselect("Unidades que veem este item", todas, key=f"{p}_clis")
    v["clis"] = [] if (not sel or set(sel) == set(todas)) else sel

    arq = None
    if cfg.get("foto"):
        if it.get("foto"):
            pend = st.session_state.fotos_novas.get(it["foto"])
            if pend:
                st.image(pend, width=240, caption="Foto atual (ainda não publicada)")
            elif SITE_URL:
                st.image(f"{SITE_URL}/{it['foto']}", width=240, caption="Foto atual")
            else:
                st.caption(f"Foto atual: {it['foto']}")
        arq = st.file_uploader("Foto (JPG ou PNG; o programa reduz sozinho)" if not it.get("foto")
                               else "Trocar foto", type=["jpg", "jpeg", "png", "webp"], key=f"{p}_foto")
    return v, arq


def aplicar(item, v, arq, area):
    """Copia os valores do formulário para o item (criando/limpando campos)."""
    gerenciados = ("sub", "tit", "txt", "mes", "data", "hora", "local", "quem", "pessoa", "link", "video", "imp",
                   "clis")
    for k in gerenciados:
        if k in v and v[k] not in ("", None, False):
            item[k] = v[k]
        elif k in item and k != "clis":
            item.pop(k)
    item["clis"] = v.get("clis", [])
    item["tit"] = v["tit"].strip()
    item["txt"] = v["txt"].strip()
    if arq is not None:
        dados = core.reduzir_foto(arq.getvalue())
        caminho = f"fotos/{item['id']}-{int(time.time())}.jpg"
        st.session_state.fotos_novas[caminho] = dados
        item["foto"] = caminho
        if core.eh_retrato(dados):
            item["retrato"] = True
        else:
            item.pop("retrato", None)
    varq = v.get("_videoarq")
    if varq is not None:
        ext = "webm" if varq.name.lower().endswith(".webm") else "mp4"
        caminho = f"videos/{item['id']}-{int(time.time())}.{ext}"
        st.session_state.fotos_novas[caminho] = varq.getvalue()
        item["video"] = caminho
    parq = v.get("_pdfarq")
    if parq is not None:
        base = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(parq.name)[0].lower()).strip("-") or item["id"]
        caminho = f"politicas/{base}-{int(time.time())}.pdf"
        st.session_state.fotos_novas[caminho] = parq.getvalue()
        item["link"] = caminho
    if area == "desafio":  # um desafio por mês
        st.session_state.dados["itens"] = [
            i for i in st.session_state.dados["itens"]
            if not (i.get("area") == "desafio" and i.get("mes") == item.get("mes") and i["id"] != item["id"])]


def novo_item(area):
    cfg = AREAS[area]
    n = st.session_state.cnt.get(area, 0)
    p = f"{area}_{n}"
    st.subheader("➕ Novo item")
    bloco_ia(p, area)
    v, arq = campos(p, area, {})
    if st.button("Adicionar ao rascunho", type="primary", key=f"{p}_add"):
        if not v["tit"].strip():
            st.warning("Preencha o título.")
            return
        item = {"id": core.novo_id(), "criado": core.agora_ms(), "area": area}
        aplicar(item, v, arq, area)
        st.session_state.dados["itens"].append(item)
        st.session_state.cnt[area] = n + 1
        marcar()
        st.session_state["_msg"] = ("success", "Item adicionado ao rascunho. Clique em Publicar (menu lateral) para o site atualizar.")
        st.rerun()


def lista_itens(area):
    itens = [i for i in st.session_state.dados["itens"] if i.get("area", "com") == area]
    itens.sort(key=lambda i: i.get("criado", 0), reverse=True)
    st.subheader(f"📋 Itens existentes ({len(itens)})")
    if not itens:
        st.caption("Nenhum item ainda.")
    for it in itens:
        rotulo = it.get("tit", "(sem título)")
        if len(rotulo) > 90:
            rotulo = rotulo[:90] + "…"
        with st.expander(rotulo):
            p = f"ed_{it['id']}"
            bloco_ia(p, area)
            v, arq = campos(p, area, it)
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("Salvar alterações", key=f"{p}_salvar", type="primary"):
                if not v["tit"].strip():
                    st.warning("O título não pode ficar vazio.")
                else:
                    aplicar(it, v, arq, area)
                    marcar()
                    st.session_state["_msg"] = ("success", "Alterações salvas no rascunho.")
                    st.rerun()
            if c2.button("🗑️ Excluir", key=f"{p}_del"):
                st.session_state.dados["itens"] = [i for i in st.session_state.dados["itens"] if i["id"] != it["id"]]
                marcar()
                st.session_state["_msg"] = ("success", "Item excluído do rascunho.")
                st.rerun()


# ------------------------------------------------------------- equipe
def tela_equipe():
    st.subheader("Pessoas, aniversários e data de admissão")
    st.caption("Edite direto na tabela (clique numa célula) e adicione linhas no final. "
               "Aniversário no formato DD/MM, por exemplo 26/04. Sem IA aqui.")
    eq = st.session_state.dados["equipe"]
    linhas = []
    for pdado in eq:
        md = pdado.get("md", "")
        linhas.append({"id": pdado.get("id", ""), "nome": pdado.get("nome", ""),
                       "unidade": pdado.get("cli", core.UNIDADES[0]),
                       "aniversario": f"{md[3:5]}/{md[0:2]}" if re.match(r"^\d\d-\d\d$", md) else "",
                       "admissao": pdado.get("adm") or None})
    df = pd.DataFrame(linhas, columns=["id", "nome", "unidade", "aniversario", "admissao"])
    df["admissao"] = pd.to_datetime(df["admissao"], errors="coerce")
    editado = st.data_editor(
        df, num_rows="dynamic", key="equipe_ed",
        column_config={
            "id": None,
            "nome": st.column_config.TextColumn("Nome", required=True),
            "unidade": st.column_config.SelectboxColumn("Unidade", options=core.UNIDADES, required=True),
            "aniversario": st.column_config.TextColumn("Aniversário (DD/MM)", max_chars=5),
            "admissao": st.column_config.DateColumn("Admissão", format="DD/MM/YYYY"),
        })
    if st.button("Salvar equipe no rascunho", type="primary"):
        antigos = {x["id"]: x for x in eq}
        novos, erros = [], []
        for _, r in editado.iterrows():
            nome = (r["nome"] or "").strip() if isinstance(r["nome"], str) else ""
            if not nome:
                continue
            pid = r["id"] if isinstance(r["id"], str) and r["id"] else core.novo_id("e")
            md = ""
            an = (r["aniversario"] or "").strip() if isinstance(r["aniversario"], str) else ""
            if an:
                m = re.match(r"^(\d{1,2})/(\d{1,2})$", an)
                try:
                    datetime(2000, int(m.group(2)), int(m.group(1)))
                    md = f"{int(m.group(2)):02d}-{int(m.group(1)):02d}"
                except (AttributeError, ValueError):
                    erros.append(f"{nome}: aniversário “{an}” inválido (use DD/MM).")
                    continue
            pessoa = dict(antigos.get(pid, {}))
            pessoa.update({"id": pid, "nome": nome, "cli": r["unidade"]})
            if md:
                pessoa["md"] = md
            else:
                pessoa.pop("md", None)
            if pd.notna(r["admissao"]):
                pessoa["adm"] = pd.Timestamp(r["admissao"]).date().isoformat()
            else:
                pessoa.pop("adm", None)
            novos.append(pessoa)
        if erros:
            for e in erros:
                st.error(e)
        else:
            st.session_state.dados["equipe"] = novos
            marcar()
            st.session_state["_msg"] = ("success", f"Equipe salva no rascunho ({len(novos)} pessoas).")
            st.rerun()


# ----------------------------------------------------------- calendário
def tela_calendario():
    st.subheader("Calendário do RH")
    st.info("O calendário do site se monta sozinho: ele junta as **datas** dos comunicados, treinamentos e "
            "eventos, os **aniversários** da equipe, os feriados e as campanhas do mês. "
            "Para pôr algo no calendário, cadastre o item com data nas outras telas.")
    linhas = []
    for i in st.session_state.dados["itens"]:
        if i.get("data"):
            linhas.append({"Data": i["data"], "Seção": AREAS.get(i.get("area", "com"), {}).get("nome", i.get("area")),
                           "Título": i.get("tit", ""), "Horário": i.get("hora", ""), "Local": i.get("local", "")})
    for pdado in st.session_state.dados["equipe"]:
        if pdado.get("md"):
            linhas.append({"Data": f"(todo ano) {pdado['md'][3:5]}/{pdado['md'][0:2]}", "Seção": "🎂 Aniversário",
                           "Título": pdado["nome"], "Horário": "", "Local": pdado.get("cli", "")})
    if linhas:
        st.dataframe(pd.DataFrame(linhas).sort_values("Data"), hide_index=True)
    else:
        st.caption("Nada com data cadastrado ainda.")


# --------------------------------------------------------------- tela
with st.sidebar:
    st.title("📰 Editor do RH")
    st.caption("Léah Estética")
    escolha = st.radio("Seção", list(AREAS), format_func=lambda a: AREAS[a]["nome"], label_visibility="collapsed")
    st.divider()
    if st.session_state.alterado:
        st.warning("Há alterações **não publicadas**.")
    else:
        st.success("Tudo publicado.")
    if st.button("🚀 Publicar no site", type="primary", disabled=not st.session_state.alterado):
        try:
            with st.spinner("Publicando…"):
                modo = core.publicar(st.session_state.dados, st.session_state.fotos_novas, gh,
                                     f"RH: atualização {datetime.now():%d/%m/%Y %H:%M}")
            st.session_state.fotos_novas = {}
            st.session_state.alterado = False
            st.session_state["_msg"] = ("success", "Publicado! O site atualiza em 1 a 2 minutos."
                                        if modo == "github" else "Salvo nos arquivos locais.")
            st.rerun()
        except Exception as e:
            st.error(f"Não foi possível publicar: {e}")
    if st.session_state.alterado and st.button("↩️ Descartar alterações"):
        st.session_state.dados = carregar_dados()
        st.session_state.fotos_novas = {}
        st.session_state.alterado = False
        st.session_state.cnt = {k: v + 1 for k, v in st.session_state.cnt.items()}
        for k in [k for k in st.session_state if str(k).startswith("ed_") or k == "equipe_ed"]:
            del st.session_state[k]
        st.rerun()
    REL_TOKEN, REL_REPO = seg("RELATORIO_TOKEN"), seg("RELATORIO_REPO")
    if REL_TOKEN and REL_REPO:
        st.divider()
        if st.button("🔄 Atualizar ranking agora"):
            try:
                core.atualizar_ranking(REL_TOKEN, REL_REPO)
                st.success("Pedido enviado! O ranking novo aparece no site em 5 a 10 minutos.")
            except Exception as e:
                st.error(f"Não foi possível atualizar: {e}")
    if SITE_URL:
        st.link_button("Abrir o site", SITE_URL)
    if "gem" in st.session_state:
        g = st.session_state.gem
        st.caption(f"IA: chave {g.atual + 1} de {len(g.chaves)}")

msg = st.session_state.pop("_msg", None)
if msg:
    getattr(st, msg[0])(msg[1])

cfg = AREAS[escolha]
st.header(cfg["nome"])
if cfg.get("ajuda"):
    st.caption(cfg["ajuda"])

if escolha == "equipe":
    tela_equipe()
elif escolha == "cal":
    tela_calendario()
else:
    novo_item(escolha)
    st.divider()
    lista_itens(escolha)
