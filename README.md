# Jornal do RH · Léah Estética

- **Site** (todos veem): `index.html` + `dados.json` + `fotos/` → GitHub Pages
- **Editor** (só a Leti): `app.py` + `core.py` → Streamlit Community Cloud, com senha

A Leti escreve o tema, clica em **Gerar com IA**, revisa o texto, adiciona a foto e clica em **Publicar**.
O editor grava `dados.json` e as fotos no GitHub e o site atualiza em 1 a 2 minutos.

## Montagem (uma vez só)

1. **Repositório no GitHub** com tudo desta pasta. Confira que `api.ini`/`keys.ini` NÃO subiram (o `.gitignore` já bloqueia).
   Coloque também a foto `fotos/novidade-obras.jpg` (a novidade atual aponta para ela e ela não veio junto com o index).
2. **GitHub Pages**: Settings → Pages → Branch `main`, pasta `/ (root)`. O site fica em `https://USUARIO.github.io/REPO`.
3. **Token do GitHub**: Settings → Developer settings → Fine-grained tokens → só este repositório → *Contents: Read and write*.
4. **Streamlit Community Cloud** (share.streamlit.io): New app → este repositório → arquivo `app.py`.
   Em *Advanced settings → Secrets*, cole o conteúdo de `.streamlit/secrets.toml.example` preenchido
   (senha da Leti, lista de chaves do Gemini, token, repositório, endereço do site).
5. Passe para a Leti o link do Streamlit e a senha.

## Chaves do Gemini
`GEMINI_KEYS` aceita várias. Se uma der erro (inválida, cota, rede), o editor pula para a próxima e gera de novo;
lembra qual funcionou por último. Rodando no seu computador, ele também lê `keys.ini` ou `api.ini` (uma chave por linha)
na mesma pasta do `app.py`. Troque (rotacione) as chaves que já circularam em conversas.

## Rodar no computador
```
pip install -r requirements.txt
streamlit run app.py
```
Sem GitHub configurado, ele grava `dados.json` e `fotos/` na própria pasta.

## Dicas
- **Manchete**: automática, é a novidade mais recente com foto ou vídeo.
- **Calendário**: monta sozinho a partir das datas dos itens, aniversários, feriados e campanhas.
- Tudo é **rascunho** até clicar em *Publicar*. A IA nunca publica sozinha.
- Campanhas do mês (Outubro Rosa etc.) e datas especiais continuam no `index.html` (variáveis `CAMP` e `ESP`).

## Animações e privacidade (novo)
- O site tem animações ao rolar (revelação dos blocos, parallax nas fotos, faixa de avisos, menu que acompanha a seção, contadores, "Ler mais", confetes ao clicar na logo ou na aniversariante). Quem tem "reduzir movimento" ligado no aparelho vê tudo sem animação.
- A lista "Nossa equipe" foi removida da página. Só aparecem: aniversariantes (do mês e no calendário) e "Tempo de Léah", que mostra apenas quem tem 1 ano ou mais de casa.
- Atenção: o `dados.json` continua público no GitHub Pages (a lista de nomes está nele, só não é exibida na página).
