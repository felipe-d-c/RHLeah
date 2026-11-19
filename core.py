"""Lógica do editor do Jornal do RH (sem dependência do Streamlit).

- Chaves do Gemini: lidas de st.secrets / variável de ambiente / keys.ini / api.ini,
  com rotação automática (se uma falha, tenta a próxima).
- Dados: dados.json (local ou no GitHub).
- Fotos: reduzidas e salvas em fotos/.
- Publicação: commit via API do GitHub (ou gravação local, se não houver GitHub configurado).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import uuid
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
UNIDADES = ["Treze Tílias", "Campos Novos", "Joaçaba", "Videira", "Administrativo", "Rota"]

MODELOS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
VERTEX_URL = "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent"

REGRAS_MARCA = (
    "Você é o RH da Léah Estética, uma rede de clínicas de estética (unidades em Treze Tílias, "
    "Campos Novos, Joaçaba e Videira). Escreva em português do Brasil, com tom acolhedor, claro e "
    "profissional, falando com as colaboradoras e colaboradores. Texto corrido, sem markdown, sem "
    "emojis e sem listas com marcadores. NÃO invente fatos, datas, horários, nomes, números ou "
    "locais: use apenas o que foi informado. Se faltar informação, escreva de forma geral."
)


class GeminiError(Exception):
    pass


# ----------------------------------------------------------------- chaves
def carregar_chaves(secrets=None) -> list[str]:
    """Lista de chaves, na ordem. Fontes: secrets GEMINI_KEYS, env GEMINI_KEYS, keys.ini, api.ini."""
    chaves: list[str] = []
    try:
        v = secrets.get("GEMINI_KEYS") if secrets is not None else None
    except Exception:
        v = None
    if v:
        chaves += list(v) if not isinstance(v, str) else re.split(r"[\s,;]+", v)
    if os.environ.get("GEMINI_KEYS"):
        chaves += re.split(r"[\s,;]+", os.environ["GEMINI_KEYS"])
    for nome in ("keys.ini", "api.ini"):
        p = BASE / nome
        if p.exists():
            for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                ln = ln.strip()
                if not ln or ln.startswith(("#", ";", "[")):
                    continue
                if "=" in ln:  # aceita "chave = AIza..."
                    ln = ln.split("=", 1)[1].strip()
                chaves.append(ln.strip("'\""))
    vistas, out = set(), []
    for c in chaves:
        c = c.strip()
        if c and c not in vistas:
            vistas.add(c)
            out.append(c)
    return out


class Gemini:
    """Cliente com rotação de chaves. Lembra a última chave que funcionou."""

    def __init__(self, chaves: list[str], timeout: int = 40):
        if not chaves:
            raise GeminiError("Nenhuma chave do Gemini encontrada (GEMINI_KEYS, keys.ini ou api.ini).")
        self.chaves = chaves
        self.timeout = timeout
        self.atual = 0
        self.mortas: set[int] = set()  # chaves com erro permanente (inválida/sem permissão)

    def _chamar(self, chave: str, modelo: str, payload: dict) -> requests.Response:
        if chave.startswith("AQ."):  # chave estilo Vertex AI (express mode)
            return requests.post(VERTEX_URL.format(model=modelo), params={"key": chave},
                                 json=payload, timeout=self.timeout)
        return requests.post(GEMINI_URL.format(model=modelo), headers={"x-goog-api-key": chave},
                             json=payload, timeout=self.timeout)

    def gerar(self, prompt: str, sistema: str = REGRAS_MARCA, json_saida: bool = False) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": sistema}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 1500},
        }
        if json_saida:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        n = len(self.chaves)
        erros: list[str] = []
        # percorre as chaves a partir da última boa; para cada chave tenta os modelos
        for passo in range(n):
            i = (self.atual + passo) % n
            if i in self.mortas:
                continue
            for modelo in MODELOS:
                try:
                    r = self._chamar(self.chaves[i], modelo, payload)
                except requests.RequestException as e:
                    erros.append(f"chave {i + 1}: rede ({type(e).__name__})")
                    break  # problema de rede: troca de chave
                if r.status_code == 200:
                    try:
                        texto = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    except (KeyError, IndexError, ValueError):
                        erros.append(f"chave {i + 1}/{modelo}: resposta vazia/bloqueada")
                        continue
                    if texto:
                        self.atual = i
                        return texto
                    continue
                if r.status_code == 404:  # modelo indisponível para esta chave: próximo modelo
                    erros.append(f"chave {i + 1}/{modelo}: modelo indisponível")
                    continue
                if r.status_code in (400, 401, 403):  # inválida/sem permissão/revogada
                    self.mortas.add(i)
                    erros.append(f"chave {i + 1}: recusada ({r.status_code})")
                    break
                # 429 (cota) e 5xx: tenta a próxima chave
                erros.append(f"chave {i + 1}: erro {r.status_code}")
                break
        raise GeminiError("Todas as chaves falharam. " + "; ".join(erros[-6:]))

    def texto(self, tema: str, linhas: int, contexto: str, extra: str = "") -> dict:
        """Gera {'titulo','texto'} para um tema, limitado a `linhas` linhas."""
        prompt = (
            f"Seção do jornal: {contexto}.\nTema informado pela RH: {tema}\n"
            + (f"Informações adicionais: {extra}\n" if extra else "")
            + f"\nEscreva um texto curto, com no máximo {linhas} linhas (parágrafos curtos). "
            "Responda APENAS em JSON no formato "
            '{"titulo": "título curto e atraente, até 80 caracteres", "texto": "o texto"}.'
        )
        bruto = self.gerar(prompt, json_saida=True)
        try:
            d = json.loads(re.sub(r"^```(?:json)?|```$", "", bruto.strip(), flags=re.M).strip())
            return {"titulo": str(d.get("titulo", "")).strip(), "texto": str(d.get("texto", "")).strip()}
        except (ValueError, AttributeError):
            return {"titulo": "", "texto": bruto}


# ------------------------------------------------------------------ dados
def novo_id(prefixo: str = "i") -> str:
    return f"{prefixo}{int(time.time())}{uuid.uuid4().hex[:4]}"


def agora_ms() -> int:
    return int(time.time() * 1000)


def validar(d: dict) -> dict:
    d.setdefault("itens", [])
    d.setdefault("equipe", [])
    return d


def carregar_local() -> dict:
    return validar(json.loads((BASE / "dados.json").read_text(encoding="utf-8")))


def limpar_item(it: dict) -> dict:
    """Remove campos vazios para manter o JSON enxuto."""
    return {k: v for k, v in it.items() if v not in ("", None, [], False) or k in ("clis",)}


def ordenar(d: dict) -> dict:
    return d


# ------------------------------------------------------------------ fotos
def reduzir_foto(dados: bytes, lado_max: int = 1600, qualidade: int = 82) -> bytes:
    from PIL import Image, ImageOps

    im = Image.open(io.BytesIO(dados))
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB",):
        fundo = Image.new("RGB", im.size, (255, 255, 255))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            fundo.paste(im, mask=im.split()[-1])
            im = fundo
        else:
            im = im.convert("RGB")
    im.thumbnail((lado_max, lado_max))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=qualidade, optimize=True)
    return buf.getvalue()


def eh_retrato(dados: bytes) -> bool:
    from PIL import Image

    w, h = Image.open(io.BytesIO(dados)).size
    return h > w * 1.2


# ----------------------------------------------------------------- GitHub
class GitHub:
    def __init__(self, token: str, repo: str, branch: str = "main"):
        self.repo, self.branch = repo, branch
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}",
                               "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})

    def _url(self, caminho: str) -> str:
        return f"https://api.github.com/repos/{self.repo}/contents/{caminho}"

    def ler(self, caminho: str) -> tuple[bytes | None, str | None]:
        r = self.s.get(self._url(caminho), params={"ref": self.branch}, timeout=30)
        if r.status_code == 404:
            return None, None
        r.raise_for_status()
        j = r.json()
        return base64.b64decode(j["content"]), j["sha"]

    def gravar(self, caminho: str, conteudo: bytes, msg: str) -> None:
        for _ in range(3):  # repete se houver conflito de sha
            _, sha = self.ler(caminho)
            corpo = {"message": msg, "branch": self.branch,
                     "content": base64.b64encode(conteudo).decode()}
            if sha:
                corpo["sha"] = sha
            r = self.s.put(self._url(caminho), json=corpo, timeout=60)
            if r.status_code in (200, 201):
                return
            if r.status_code in (409, 422):
                time.sleep(1)
                continue
            r.raise_for_status()
        raise RuntimeError(f"Não consegui gravar {caminho} no GitHub.")

    def apagar(self, caminho: str, msg: str) -> None:
        _, sha = self.ler(caminho)
        if sha:
            r = self.s.delete(self._url(caminho), json={"message": msg, "sha": sha, "branch": self.branch},
                              timeout=30)
            r.raise_for_status()


def publicar(dados: dict, fotos_novas: dict[str, bytes], gh: GitHub | None, msg: str = "Atualização do RH") -> str:
    """Grava fotos + dados.json. Retorna 'github' ou 'local'."""
    conteudo = json.dumps(dados, ensure_ascii=False, indent=1).encode("utf-8")
    if gh is None:
        for caminho, b in fotos_novas.items():
            p = BASE / caminho
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
        (BASE / "dados.json").write_bytes(conteudo)
        return "local"
    for caminho, b in fotos_novas.items():  # fotos primeiro, para o site nunca apontar pra foto inexistente
        gh.gravar(caminho, b, f"{msg} (foto)")
    gh.gravar("dados.json", conteudo, msg)
    return "github"


def carregar_remoto(gh: GitHub | None) -> dict:
    if gh is None:
        return carregar_local()
    b, _ = gh.ler("dados.json")
    return validar(json.loads(b.decode("utf-8"))) if b else carregar_local()


def atualizar_ranking(token: str, repo: str, workflow: str = "precache.yml", ref: str = "main") -> None:
    """Dispara o GitHub Action do repositório do relatório comercial (baixa da Belle e publica o ranking.json)."""
    r = requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"},
                      json={"ref": ref}, timeout=30)
    if r.status_code != 204:
        raise RuntimeError(f"GitHub respondeu {r.status_code}: {r.text[:200]}")
