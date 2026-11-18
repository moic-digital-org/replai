#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Replai · LinkedIn: leitura pela Voyager, curtir/comentar na tela e o navegador.
"""A Voyager e' a API interna que o proprio site do LinkedIn consome. Daqui so' sai GET: o post do
lead, o comentario da conta e "quem sou eu". Curtir e comentar NAO passam por aqui (sao clique real
na tela, no replai_bot), pela mesma razao que o DM da prospeccao e' digitado: a escrita e' a parte
que o LinkedIn vigia, e ela tem de parecer exatamente o que e', uma pessoa usando o site.

DE ONDE VEIO. Porte para Python do `src/lib/voyager/` da extensao Replai Comercial (2026-09-24),
que ja' rodava esses mesmos endpoints na sessao de cada BD:
  GET /me                                             quem esta' logado (URN + vanity)
  GET /identity/dash/profiles?q=memberIdentity        vanity -> URN (so' quando o CRM nao tem o URN)
  GET /identity/profileUpdatesV2?q=memberShareFeed    posts de um perfil
  GET /feed/comments?q=comments&updateId=activity:N   comentarios de um post
A chamada sai de DENTRO da pagina (`page.evaluate` com `fetch`), com os cookies da propria sessao,
como o `perfil_bot` e o `chats_motor.js` ja' fazem: nada de token, nada de servidor.

A Voyager responde em dois formatos, e os parsers aceitam os dois:
  - normalizado: {data: {..., "*elements": [urn...]}, included: [obj...]}; refs "*campo" apontam
    para objetos em `included` pelo `entityUrn` (o `hidratar` resolve);
  - simples: {elements: [...], paging, metadata}.
Os extratores procuram cada campo por mais de um nome porque o schema muda com frequencia: post sem
algum campo entra com o campo vazio em vez de quebrar a rodada.

A DATA DO POST sai do proprio id da activity (os 41 bits altos sao ms desde 1970): a Voyager so'
devolve tempo relativo ("3d").

ERROS (mesma tabela do client.ts do Replai):
  status 0 / 3xx (redirect para login/checkpoint), 429, 999 ...... BLOQUEIO: para a rodada
  401 ............................................................ SESSAO expirada: para a rodada
  403 ............................................................ recusa; 3 seguidas = BLOQUEIO
  404 / 410 ...................................................... nao encontrado
  outro nao-ok ................................................... http
"""
import json
import os
import random
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# ----------------------------------------------------------------------------
# A chamada, dentro da pagina.
# ----------------------------------------------------------------------------
# `redirect: 'manual'` e' o que deixa o redirect para login/checkpoint aparecer como status 0
# (opaqueredirect) em vez de virar um HTML 200 que quebraria o JSON. Mesmo header `normalized+json`
# do perfil_bot: sem ele o `included` (onde moram os campos) nao vem.
JS_VOYAGER_GET = """
async ([caminho]) => {
  const csrf = (document.cookie.match(/JSESSIONID="?([^";]+)"?/) || [])[1] || '';
  let r;
  try {
    r = await fetch('/voyager/api' + caminho, {
      headers: { 'csrf-token': csrf,
                 'accept': 'application/vnd.linkedin.normalized+json+2.1',
                 'x-restli-protocol-version': '2.0.0' },
      credentials: 'include', redirect: 'manual' });
  } catch (e) {
    return JSON.stringify({ status: -1, erro: String(e) });
  }
  const st = r.type === 'opaqueredirect' ? 0 : r.status;
  let j = null;
  if (r.ok) {
    try { j = await r.json(); } catch (e) { return JSON.stringify({ status: st, erro: 'nao-json' }); }
  }
  return JSON.stringify({ status: st, j: j });
}
"""

ERRO_BLOQUEIO = "bloqueio"
ERRO_SESSAO = "sessao"
ERRO_NAO_ENCONTRADO = "nao_encontrado"
ERRO_HTTP = "http"
ERRO_REDE = "rede"


class VoyagerErro(Exception):
    """Falha de leitura, com o TIPO (bloqueio/sessao/nao_encontrado/http/rede) e o status."""

    def __init__(self, tipo, msg, status=None):
        super().__init__(msg)
        self.tipo = tipo
        self.status = status


def classificar_status(status, recusas_403_seguidas, limite_403=3):
    """(tipo_do_erro ou None, recusas_403_seguidas_atualizado). Puro (testado).

    None = resposta boa. O contador de 403 so' zera numa resposta que NAO e' 403: e' a SEQUENCIA que
    denuncia limite de conta (403 salpicado e' perfil restrito, normal)."""
    if status == -1:
        return ERRO_REDE, recusas_403_seguidas
    if status == 0 or (status is not None and 300 <= status < 400):
        return ERRO_BLOQUEIO, recusas_403_seguidas
    if status in (429, 999):
        return ERRO_BLOQUEIO, recusas_403_seguidas
    if status == 401:
        return ERRO_SESSAO, recusas_403_seguidas
    if status == 403:
        n = recusas_403_seguidas + 1
        return (ERRO_BLOQUEIO if n >= limite_403 else ERRO_HTTP), n
    if status in (404, 410):
        return ERRO_NAO_ENCONTRADO, 0
    if status is None or not (200 <= status < 300):
        return ERRO_HTTP, 0
    return None, 0


# ----------------------------------------------------------------------------
# Parsers (puros). Porte 1:1 do parse.ts do Replai Comercial, com os mesmos testes.
# ----------------------------------------------------------------------------
_MAX_PROFUNDIDADE = 10


def _obj(v):
    return isinstance(v, dict)


def hidratar(raiz):
    """Formato normalizado -> simples, resolvendo as refs `*campo` pelo `entityUrn` do `included`."""
    if not _obj(raiz):
        return {}
    if not isinstance(raiz.get("included"), list):
        return raiz
    indice = {it["entityUrn"]: it for it in raiz["included"]
              if _obj(it) and isinstance(it.get("entityUrn"), str)}

    def resolver(v, prof):
        if prof > _MAX_PROFUNDIDADE:
            return v
        if isinstance(v, list):
            return [resolver(x, prof + 1) for x in v]
        if not _obj(v):
            return v
        out = {}
        for k, val in v.items():
            if k.startswith("*"):
                chave = k[1:]

                def deref(u):
                    return resolver(indice[u], prof + 1) if isinstance(u, str) and u in indice else u
                out[chave] = [deref(x) for x in val] if isinstance(val, list) else deref(val)
            else:
                out[k] = resolver(val, prof + 1)
        return out

    data = raiz.get("data") if _obj(raiz.get("data")) else {}
    return resolver(data, 0)


def elementos(hidratado):
    els = hidratado.get("elements") if _obj(hidratado) else None
    return [e for e in els if _obj(e)] if isinstance(els, list) else []


def percorrer(v, visitar, prof=0):
    """Visita todo dict (inclusive dentro de listas), em profundidade."""
    if prof > 40:
        return
    if isinstance(v, list):
        for x in v:
            percorrer(x, visitar, prof + 1)
    elif _obj(v):
        visitar(v)
        for x in v.values():
            percorrer(x, visitar, prof + 1)


def _texto_de(v):
    if isinstance(v, str):
        return v
    if _obj(v):
        if isinstance(v.get("text"), str):
            return v["text"]
        if _obj(v.get("text")) and isinstance(v["text"].get("text"), str):
            return v["text"]["text"]
    return None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


_RE_ACTIVITY = re.compile(r"urn:li:activity:(\d+)")


def data_da_activity(activity_id, agora_ms=None):
    """ISO (UTC) da data do post a partir do id da activity, ou None.

    Os 41 bits mais altos do id sao ms desde 1970 (`id >> 22`). Recusa ano < 2003 e data no futuro
    (id que nao e' de activity, ou lixo)."""
    s = str(activity_id or "")
    if not re.fullmatch(r"\d{10,25}", s):
        return None
    ms = int(s) >> 22
    agora_ms = agora_ms if agora_ms is not None else int(time.time() * 1000)
    if ms > agora_ms + 86_400_000:
        return None
    try:
        from datetime import datetime, timezone
        d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    if d.year < 2003:
        return None
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


def activity_id_de(*candidatos):
    for c in candidatos:
        if isinstance(c, str):
            m = _RE_ACTIVITY.search(c)
            if m:
                return m.group(1)
    return None


def url_do_post(activity_urn):
    return f"https://www.linkedin.com/feed/update/{activity_urn}/"


def vanity_da_url(url):
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "", re.I)
    if not m:
        return None
    from urllib.parse import unquote
    return unquote(m.group(1))


def _contagens(el):
    sd = el.get("socialDetail") if _obj(el.get("socialDetail")) else None
    if not sd:
        return None
    for k in ("totalSocialActivityCounts", "socialActivityCounts"):
        if _obj(sd.get(k)):
            return sd[k]
    return None


def _primeira_imagem(conteudo):
    achado = []

    def visitar(o):
        if achado:
            return
        if isinstance(o.get("rootUrl"), str) and isinstance(o.get("artifacts"), list) and o["artifacts"]:
            arts = [a for a in o["artifacts"] if _obj(a)]
            arts.sort(key=lambda a: _num(a.get("width")) or 0, reverse=True)
            pick = next((a for a in arts if (_num(a.get("width")) or 0) <= 800),
                        arts[-1] if arts else None)
            seg = (pick or {}).get("fileIdentifyingUrlPathSegment")
            if isinstance(seg, str):
                achado.append(o["rootUrl"] + seg)
        elif isinstance(o.get("url"), str) and "media.licdn.com" in o["url"]:
            achado.append(o["url"])
    percorrer(conteudo, visitar)
    return achado[0] if achado else None


def ler_post(el):
    """Um post do `profileUpdatesV2` -> dict, ou None se nao der para achar a activity."""
    meta = el.get("updateMetadata") if _obj(el.get("updateMetadata")) else {}
    activity_id = activity_id_de(meta.get("urn"), el.get("urn"), el.get("entityUrn"),
                                 meta.get("shareUrn"))
    if not activity_id:
        return None
    activity_urn = f"urn:li:activity:{activity_id}"
    ator = el.get("actor") if _obj(el.get("actor")) else {}
    nav = ator.get("navigationContext") if _obj(ator.get("navigationContext")) else {}
    texto = _texto_de(el.get("commentary")) or ""
    repost = el.get("resharedUpdate") if _obj(el.get("resharedUpdate")) else None
    cont = _contagens(el) or {}
    reacao = cont.get("reactionByViewer")
    curtido = (cont.get("liked") is True
               or (isinstance(reacao, str) and reacao != "")
               or _obj(reacao))
    return {
        "activity_urn": activity_urn,
        "activity_id": activity_id,
        "url": url_do_post(activity_urn),
        "data": data_da_activity(activity_id),
        "texto": texto,
        "autor": _texto_de(ator.get("name")),
        "autor_headline": _texto_de(ator.get("description")),
        "autor_vanity": vanity_da_url(nav.get("actionTarget") if isinstance(nav.get("actionTarget"), str)
                                      else None),
        "repost": bool(repost),
        # O post original de um repost: o Replai compara os dois ids para nunca comentar o mesmo
        # conteúdo duas vezes (spec §3, camada 4).
        "original_id": (activity_id_de((repost.get("updateMetadata") or {}).get("urn")
                                       if _obj(repost.get("updateMetadata")) else None,
                                       repost.get("urn"), repost.get("entityUrn"))
                        if repost else None),
        # Repost sem texto proprio: o conteudo e' de outra pessoa (fica de fora do engajamento).
        "repost_puro": bool(repost) and not texto.strip(),
        "n_curtidas": _num(cont.get("numLikes")),
        "n_comentarios": _num(cont.get("numComments")),
        "n_compartilhamentos": _num(cont.get("numShares")),
        "curtido_pela_conta": bool(curtido),
        "imagem": _primeira_imagem(el.get("content"))
                  or (_primeira_imagem(repost.get("content")) if repost else None),
    }


def ler_posts(raw):
    """(posts, token_de_paginacao, total_de_elementos) de uma resposta do `profileUpdatesV2`."""
    h = hidratar(raw)
    els = elementos(h)
    posts = [p for p in (ler_post(e) for e in els) if p]
    meta = h.get("metadata") if _obj(h.get("metadata")) else {}
    tok = meta.get("paginationToken") if isinstance(meta.get("paginationToken"), str) else None
    return posts, tok, len(els)


_RE_PERFIL_URN = re.compile(r"^urn:li:(?:fsd_profile|fs_profile|fs_miniProfile):([A-Za-z0-9_-]+)$")


def perfis_na_resposta(raw):
    """[{urn, vanity, nome}] de todo perfil citado numa resposta."""
    hits = {}

    def visitar(o):
        urn = o.get("entityUrn") if isinstance(o.get("entityUrn"), str) else (
            o.get("dashEntityUrn") if isinstance(o.get("dashEntityUrn"), str) else None)
        m = _RE_PERFIL_URN.match(urn or "")
        if not m:
            return
        h = hits.setdefault(m.group(1), {"urn": m.group(1), "vanity": None, "nome": None})
        if isinstance(o.get("publicIdentifier"), str):
            h["vanity"] = o["publicIdentifier"]
        nomes = [o.get("firstName"), o.get("lastName")]
        nomes = [n for n in nomes if isinstance(n, str) and n]
        if nomes:
            h["nome"] = " ".join(nomes)
    percorrer(raw, visitar)
    return list(hits.values())


def ler_me(raw):
    """{urn, vanity, nome} da conta logada (resposta do /me), ou None."""
    com_vanity = [h for h in perfis_na_resposta(raw) if h.get("vanity")]
    return com_vanity[0] if com_vanity else None


def urn_do_perfil(raw, vanity):
    """URN (`ACoAA...`) do perfil com essa vanity numa resposta de perfil, ou None."""
    hits = perfis_na_resposta(raw)
    alvo = (vanity or "").lower()
    exato = next((h for h in hits if (h.get("vanity") or "").lower() == alvo), None)
    if exato:
        return exato["urn"]
    return hits[0]["urn"] if len(hits) == 1 else None


_CHAVES_AUTOR = re.compile(r"^(commenter|commenterForDashConversion|commenterProfile|actor|author)$",
                           re.I)


def e_da_pessoa(el, me):
    """True se o comentario foi ESCRITO por `me` ({urn, vanity}). Olha so' quem escreveu, nunca o
    texto: uma mencao a conta no comentario de outra pessoa tambem carrega o URN dela."""
    arvores = [v for k, v in el.items() if _CHAVES_AUTOR.match(k.lstrip("*"))]
    if not arvores:
        return False
    s = json.dumps(arvores, ensure_ascii=False)
    if me.get("urn") and me["urn"] in s:
        return True
    return bool(me.get("vanity")) and f'"publicIdentifier": "{me["vanity"]}"' in s


def urn_do_comentario(el):
    if isinstance(el.get("urn"), str) and el["urn"].startswith("urn:li:comment:"):
        return el["urn"]
    eu = el.get("entityUrn")
    if isinstance(eu, str):
        # urn:li:fs_objectComment:(7123,activity:7100)  ->  urn:li:comment:(activity:7100,7123)
        m = re.match(r"^urn:li:fs_objectComment:\((\d+),((?:activity|ugcPost|share):\d+)\)$", eu)
        if m:
            return f"urn:li:comment:({m.group(2)},{m.group(1)})"
        if eu.startswith("urn:li:comment:"):
            return eu
    m = re.search(r"urn:li:comment:\([^)]+\)", json.dumps(el, ensure_ascii=False))
    return m.group(0) if m else None


def comentario_da_pessoa(raw, me):
    """{comment_urn, texto} do comentario de `me` numa resposta do /feed/comments, ou None."""
    for el in elementos(hidratar(raw)):
        if not e_da_pessoa(el, me):
            continue
        urn = urn_do_comentario(el)
        if not urn:
            continue
        texto = _texto_de(el.get("commentV2") if _obj(el.get("commentV2")) else el.get("commentary"))
        return {"comment_urn": urn, "texto": texto or _texto_de(el.get("comment"))}
    return None


def url_do_comentario(activity_urn, comment_urn):
    from urllib.parse import quote
    return f"https://www.linkedin.com/feed/update/{activity_urn}/?commentUrn={quote(comment_urn, safe='')}"


# ----------------------------------------------------------------------------
# O cliente: uma leitura por vez, com pausa, contada no teto do dia.
# ----------------------------------------------------------------------------
class Voyager:
    """Leituras pela pagina aberta. NAO dorme por conta propria entre chamadas: o ritmo e' do
    agendador do bot, que usa o intervalo entre leituras para outras coisas (e' o paralelismo da
    rodada). `pronta()` diz se ja' pode ler; `ler()` respeita o intervalo mesmo se chamada cedo,
    como rede de seguranca.

    `ao_ler(tipo)` e' chamado a cada request feita (o bot grava no journal, que e' de onde sai o
    teto do dia). `limite_403` vem do config.REPLAI_LEITURA_403_SEGUIDOS_ABORTA."""

    def __init__(self, page, pausa_seg=(3, 8), limite_403=3, ao_ler=None, rng=None,
                 relogio=time.monotonic, dormir=time.sleep):
        self.page = page
        self.pausa_seg = pausa_seg
        self.limite_403 = limite_403
        self.ao_ler = ao_ler
        self.rng = rng or random.Random()
        self.relogio = relogio
        self.dormir = dormir
        self.recusas_403 = 0
        self.proxima_em = 0.0
        self.feitas = 0

    def pronta(self):
        return self.relogio() >= self.proxima_em

    def segundos_ate_pronta(self):
        return max(0.0, self.proxima_em - self.relogio())

    def ler(self, caminho, tipo="leitura"):
        espera = self.segundos_ate_pronta()
        if espera > 0:
            self.dormir(espera)
        try:
            url = getattr(self.page, "url", None)
            if isinstance(url, str) and "linkedin.com" not in url:
                # a aba é das duas redes: a leitura usa o cookie do LinkedIn, então volta para ele antes
                self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            for tentativa in range(3):
                try:
                    bruto = self.page.evaluate(JS_VOYAGER_GET, [caminho])
                    break
                except Exception as e:  # noqa: BLE001
                    # a pagina ainda navegava (o LinkedIn termina de carregar depois do goto): espera
                    # assentar e tenta de novo; qualquer outro erro segue como antes
                    if tentativa == 2 or not re.search(r"context was destroyed|navigat", str(e), re.I):
                        raise
                    try:
                        self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:  # noqa: BLE001
                        pass
                    self.dormir(1.5)
            r = json.loads(bruto) if isinstance(bruto, str) else (bruto or {})
        except Exception as e:  # noqa: BLE001 - pagina fechada/navegando: erro de rede, nao bloqueio
            r = {"status": -1, "erro": f"{type(e).__name__}: {e}"}
        finally:
            self.feitas += 1
            self.proxima_em = self.relogio() + self.rng.uniform(*self.pausa_seg)
            if self.ao_ler:
                self.ao_ler(tipo)
        status = r.get("status")
        erro, self.recusas_403 = classificar_status(status, self.recusas_403, self.limite_403)
        if erro:
            raise VoyagerErro(erro, f"{tipo}: LinkedIn respondeu {status}"
                                    + (f" ({r.get('erro')})" if r.get("erro") else ""), status)
        if r.get("erro"):
            raise VoyagerErro(ERRO_HTTP, f"{tipo}: {r.get('erro')}", status)
        return r.get("j") or {}

    # ---- operacoes ----
    def me(self):
        me = ler_me(self.ler("/me", "me"))
        if not me or not me.get("vanity"):
            raise VoyagerErro(ERRO_SESSAO, "nao consegui identificar a conta logada (/me)")
        return me

    def urn_do_perfil(self, vanity):
        from urllib.parse import quote
        raw = self.ler("/identity/dash/profiles?q=memberIdentity&memberIdentity=" + quote(vanity),
                       "perfil")
        urn = urn_do_perfil(raw, vanity)
        if not urn:
            raise VoyagerErro(ERRO_NAO_ENCONTRADO, f"perfil {vanity} sem URN na resposta")
        return urn

    def posts(self, urn, count=20):
        caminho = ("/identity/profileUpdatesV2?q=memberShareFeed&moduleKey=member-shares%3Aphone"
                   "&includeLongTermHistory=true&profileUrn=urn%3Ali%3Afsd_profile%3A" + urn
                   + f"&count={int(count)}&start=0")
        posts, _tok, _total = ler_posts(self.ler(caminho, "posts"))
        return posts

    def comentario_da_conta(self, activity_id, me):
        caminho = ("/feed/comments?q=comments&sortOrder=REVERSE_CHRONOLOGICAL"
                   f"&updateId=activity%3A{activity_id}&count=100&start=0")
        return comentario_da_pessoa(self.ler(caminho, "comentarios"), me)


# ----------------------------------------------------------------------------
# A TELA DO POST (as unicas linhas que conhecem o DOM do LinkedIn; se ele mudar, o ajuste e' aqui)
# ----------------------------------------------------------------------------
# O JS acha os controles do post e os MARCA com `data-replai` (like, comment, editor, submit), para o
# Playwright clicar por seletor estavel e com clique real. Bilingue (EN/PT/ES). Escopo: o container do
# proprio post (pelo id da activity), nunca a pagina inteira: a pagina de um post tambem mostra outros
# posts ("mais do autor"), e curtir o post errado e' pior que nao curtir.
#
# Tres regras de seguranca, todas fail-closed (revisao de 2026-10-08):
#   - SEM o container DESTE post (achado pelo id da activity) a pagina e' "irreconhecivel": nada de
#     cair no primeiro post da pagina, que pode ser outro;
#   - o EDITOR tem de estar DENTRO do container e de uma caixa de comentario, e nunca dentro da bolha
#     de mensagem (`msg-overlay`/`msg-form`): o mesmo perfil de Chrome abre conversas na prospeccao, e
#     um editor generico casaria com a caixa do DM;
#   - o estado da curtida volta CRU (o `aria-pressed`): 'true', 'false' ou null. So' 'false' explicito
#     autoriza o clique, porque clicar numa curtida existente a desfaz.
JS_CONTROLES = r"""
([actId]) => {
  const norm = s => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  document.querySelectorAll('[data-replai]').forEach(e => e.removeAttribute('data-replai'));
  let box = null;
  if (actId) {
    for (const a of ['data-urn', 'data-id', 'data-activity-urn', 'data-entity-urn']) {
      box = document.querySelector(`[${a}*="${actId}"]`);
      if (box) break;
    }
  }
  const CHAT = el => !!el.closest('[class*="msg-overlay"], [class*="msg-form"], .msg-form__contenteditable');
  const TEXTBOX = '[role="textbox"][contenteditable="true"]';
  // Layout novo (visto em 27/10/2026): sem data-urn nem classes estáveis. O curtir diz o estado no rótulo
  // ("Situação do botão de reação: nenhuma reação"). Parte do que carrega o id DESTE post e sobe até o
  // primeiro bloco com exatamente um curtir desses e a caixa de comentário; dois curtir = dois posts:
  // ambíguo, para (fail-closed).
  const RX_ESTADO = /^(situa[cç][aã]o do bot[aã]o de rea[cç][aã]o|reaction button state|estado del bot[oó]n de reacci[oó]n)/;
  let novo = false;
  if (!box && actId) {
    const ancoras = [...document.querySelectorAll(`[data-testid*="${actId}"], a[href*="${actId}"]`)];
    for (const a of ancoras) {
      for (let e = a.parentElement; e && e !== document.body; e = e.parentElement) {
        const n = [...e.querySelectorAll('button')].filter(b => vis(b) && RX_ESTADO.test(norm(b.getAttribute('aria-label')))).length;
        if (n > 1) break;
        if (n === 1 && [...e.querySelectorAll(TEXTBOX)].some(x => !CHAT(x))) { box = e; novo = true; break; }
      }
      if (box) break;
    }
  }
  if (!box) {
    const algum = document.querySelector('main .feed-shared-update-v2, main article');
    return JSON.stringify({ achou_post: false, tem_algum_post: !!algum });
  }
  const raiz = box;
  const rot = el => norm((el.getAttribute('aria-label') || '') + ' ' + (el.innerText || ''));
  const botoes = [...raiz.querySelectorAll('button')].filter(b => vis(b) && !CHAT(b));
  const RX_LIKE = /\b(react like|like|gostei|curtir|me gusta|recomendar)\b/;
  const RX_NAO_LIKE = /\breactions?\b|\brea[cç][oõ]es\b|\bpessoas\b|\bpeople\b|\bothers\b|\boutr[ao]s\b/;
  let like = null, pressionado = null;
  if (novo) {
    like = botoes.find(b => RX_ESTADO.test(norm(b.getAttribute('aria-label'))));
    // só "nenhuma reação" autoriza o clique; qualquer outro estado conta como já reagido
    pressionado = /(nenhuma rea[cç][aã]o|no reaction|ninguna reacci[oó]n)$/.test(norm(like.getAttribute('aria-label'))) ? 'false' : 'true';
  } else {
    like = raiz.querySelector('button.react-button__trigger');
    if (!like || !vis(like)) like = botoes.find(b => RX_LIKE.test(rot(b)) && !RX_NAO_LIKE.test(rot(b)));
    pressionado = like ? like.getAttribute('aria-pressed') : null;
  }
  const RX_COM = /^(comment|comentar|comentario|comentário)\b/;
  let com = raiz.querySelector('button.comment-button');
  if (!com || !vis(com)) com = botoes.find(b => RX_COM.test(norm(b.getAttribute('aria-label') || b.innerText || '')));
  const eds = [...raiz.querySelectorAll('.comments-comment-box [contenteditable="true"], .comments-comment-texteditor [contenteditable="true"]' + (novo ? ', ' + TEXTBOX : ''))]
    .filter(e => vis(e) && !CHAT(e));
  const ed = eds[0] || null;
  const RX_ENVIAR = /^(comment|post|comentar|publicar|publish)$/;
  let sub = null;
  if (ed) {
    const form = ed.closest('form') || ed.closest('.comments-comment-box');
    if (form && raiz.contains(form) && !CHAT(form)) {
      const bs = [...form.querySelectorAll('button')].filter(vis);
      sub = bs.find(b => /comments-comment-box__submit-button/.test(b.className))
         || bs.find(b => RX_ENVIAR.test(norm(b.innerText)));
    }
    // layout novo: sem form; o enviar ("Comentar", com texto) aparece perto do editor depois de digitar
    for (let e = ed.parentElement, i = 0; !sub && novo && e && e !== raiz && i < 8; e = e.parentElement, i++)
      sub = [...e.querySelectorAll('button')].find(b => vis(b) && !CHAT(b) && RX_ENVIAR.test(norm(b.innerText)));
  }
  if (like) like.setAttribute('data-replai', 'like');
  if (com) com.setAttribute('data-replai', 'comment');
  if (ed) ed.setAttribute('data-replai', 'editor');
  if (sub) sub.setAttribute('data-replai', 'submit');
  return JSON.stringify({
    achou_post: true, layout: novo ? 'novo' : 'antigo',
    like: { achou: !!like, pressionado: pressionado,
            rotulo: like ? rot(like).slice(0, 60) : null },
    comentar: { achou: !!com, rotulo: com ? rot(com).slice(0, 40) : null },
    editor: !!ed,
    enviar: { achou: !!sub, desabilitado: sub ? (sub.disabled || sub.getAttribute('aria-disabled') === 'true') : null,
              rotulo: sub ? norm(sub.innerText).slice(0, 30) : null },
  });
}
"""

# Comentarios VISIVEIS na pagina do post: algum e' do perfil da conta? E o trecho do nosso texto
# apareceu (a confirmacao depois de publicar)? Le' so' os itens de comentario, nunca o editor.
JS_COMENTARIOS = r"""
([vanity, trecho]) => {
  const norm = s => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();
  const itens = [...document.querySelectorAll('article.comments-comment-entity, .comments-comment-item, [data-id^="urn:li:comment"], ' +
                                              '[componentkey^="replaceableComment_urn:li:comment"]')];
  const daConta = vanity ? itens.some(it => [...it.querySelectorAll('a[href*="/in/"]')]
      .some(a => norm(decodeURIComponent(a.getAttribute('href') || '')).includes('/in/' + norm(vanity)))) : false;
  const t = norm(trecho);
  const comTrecho = t ? itens.some(it => norm(it.innerText).includes(t)) : false;
  return JSON.stringify({ n: itens.length, da_conta: daConta, com_trecho: comTrecho });
}
"""


def _json(page, js, args):
    try:
        bruto = page.evaluate(js, args)
        return json.loads(bruto) if isinstance(bruto, str) else (bruto or {})
    except Exception as e:  # noqa: BLE001 - pagina navegando/fechada: nao afirma nada
        return {"erro": f"{type(e).__name__}: {e}"}


def controles(page, activity_id):
    return _json(page, JS_CONTROLES, [str(activity_id or "")])


def comentarios_na_pagina(page, vanity, trecho=""):
    return _json(page, JS_COMENTARIOS, [vanity or "", trecho or ""])


def _trecho(texto, n=40):
    return " ".join((texto or "").split())[:n]


_MOTIVOS_PLAYWRIGHT = (("intercepts pointer events", "outro elemento cobre o botão"),
                       ("not visible", "o elemento não está visível"),
                       ("not stable", "o elemento não parou de se mexer"),
                       ("not attached", "a página redesenhou o elemento"),
                       ("not enabled", "o elemento está desabilitado"),
                       ("outside of the viewport", "o elemento ficou fora da tela"))


def motivo_do_erro(e):
    """O porquê de um erro do Playwright em português curto (o tipo sozinho, 'TimeoutError', não
    diz nada): é o que vai para o registro e para o relatório."""
    texto = str(e)
    for chave, motivo in _MOTIVOS_PLAYWRIGHT:
        if chave in texto:
            return f"{type(e).__name__}: {motivo}"
    if "visible, enabled and stable" in texto:
        return f"{type(e).__name__}: o botão apareceu mas não ficou pronto para o clique"
    if "waiting for" in texto:
        return f"{type(e).__name__}: o elemento não apareceu na página"
    return type(e).__name__


def esperar_controles(page, activity_id, pronto, segundos=8):
    """Os controles do post assim que `pronto(c)` (o LinkedIn monta a barra e o editor aos poucos)."""
    c = controles(page, activity_id)
    for _ in range(segundos * 2):
        if pronto(c):
            break
        page.wait_for_timeout(500)
        c = controles(page, activity_id)
    return c


def curtir(page, activity_id):
    """(ok, motivo, fase). fase = 'pre_clique' (nada saiu, com certeza) | 'pos_clique'."""
    c = esperar_controles(page, activity_id, lambda c: (c.get("like") or {}).get("achou"))
    if not (c.get("like") or {}).get("achou"):
        return False, "botao de curtir nao achado", "pre_clique"
    estado = c["like"].get("pressionado")
    if estado == "true":
        return False, "ja' curtido (clicar de novo descurtiria)", "pre_clique"
    if estado != "false":
        return False, f"estado da curtida desconhecido (aria-pressed={estado!r}): nao clico", "pre_clique"
    try:
        page.locator('[data-replai="like"]').first.click(timeout=8000)
    except Exception as e:  # noqa: BLE001 - o clique pode ter saido antes da excecao: INCERTO
        return False, f"clique de curtir deu excecao ({motivo_do_erro(e)}); pode ter saido", "pos_clique"
    depois = esperar_controles(page, activity_id, lambda c: (c.get("like") or {}).get("pressionado") == "true", 5)
    if (depois.get("like") or {}).get("pressionado") == "true":
        return True, "ok", "pos_clique"
    return False, "curtida nao confirmada (aria-pressed nao virou)", "pos_clique"


def _focar_editor(page):
    """Clica no editor; se o clique não pega (algo cobre, a página redesenhou), põe o foco nele direto.
    Devolve None ou o motivo de não ter conseguido."""
    editor = page.locator('[data-replai="editor"]').first
    try:
        editor.scroll_into_view_if_needed(timeout=5000)
        editor.click(timeout=8000)
        return None
    except Exception as e:  # noqa: BLE001
        motivo = motivo_do_erro(e)
    focou = page.evaluate("""() => { const e = document.querySelector('[data-replai="editor"]');
                                     if (!e) return false; e.focus();
                                     return document.activeElement === e || e.contains(document.activeElement); }""")
    return None if focou else motivo


def _clicar_publicar(page, vanity, texto):
    """Clica em publicar. None = clicou; senão o motivo (INCERTO: o clique pode ter saído).
    Com outro elemento por cima do botão o Playwright confere o alvo antes e não clica (16/11, conta
    real: o comentário morria como incerto). Aí confere a página e, sem o comentário lá, clica pelo
    próprio botão, uma vez."""
    try:
        page.locator('[data-replai="submit"]').first.click(timeout=8000)
        return None
    except Exception as e:  # noqa: BLE001 - o clique pode ter saido antes da excecao: INCERTO
        if "intercepts pointer events" not in str(e):
            return f"clique em publicar deu excecao ({motivo_do_erro(e)}); pode ter saido"
        motivo = motivo_do_erro(e)
    if comentarios_na_pagina(page, vanity, _trecho(texto)).get("com_trecho"):
        return None
    try:
        if page.evaluate("""() => { const b = document.querySelector('[data-replai="submit"]');
                                    if (!b || b.disabled) return false; b.click(); return true; }"""):
            return None
    except Exception:  # noqa: BLE001
        pass
    return f"clique em publicar deu excecao ({motivo}); pode ter saido"


def comentar(page, activity_id, texto, vanity, rng=random):
    """(ok, motivo, fase). Digita com input REAL (o LinkedIn ignora .fill) e publica. FAIL-CLOSED:
    sem editor, sem botao, ou botao desabilitado -> nada sai. Confirma pelo trecho na lista."""
    c = esperar_controles(page, activity_id, lambda c: c.get("editor") or (c.get("comentar") or {}).get("achou"))
    if not c.get("editor"):
        if not (c.get("comentar") or {}).get("achou"):
            return False, "nem editor nem botao de comentar", "pre_clique"
        try:
            page.locator('[data-replai="comment"]').first.click(timeout=8000)
        except Exception as e:  # noqa: BLE001
            return False, f"clique em comentar falhou ({motivo_do_erro(e)})", "pre_clique"
        c = esperar_controles(page, activity_id, lambda c: c.get("editor"), 6)
        if not c.get("editor"):
            return False, "o editor de comentario nao abriu", "pre_clique"
    try:
        falhou = _focar_editor(page)
        if falhou:
            return False, f"digitacao falhou ({falhou})", "pre_clique"
        page.wait_for_timeout(400)
        page.keyboard.type(texto, delay=int(rng.uniform(18, 38)))
    except Exception as e:  # noqa: BLE001
        return False, f"digitacao falhou ({motivo_do_erro(e)})", "pre_clique"
    page.wait_for_timeout(1200)
    c = controles(page, activity_id)
    env = c.get("enviar") or {}
    if not env.get("achou"):
        return False, "botao de publicar nao achado", "pre_clique"
    if env.get("desabilitado"):
        return False, "botao de publicar DESABILITADO", "pre_clique"
    falhou = _clicar_publicar(page, vanity, texto)
    if falhou:
        return False, falhou, "pos_clique"
    page.wait_for_timeout(4000)
    # Daqui para baixo o clique JA' ACONTECEU: toda saida e' pos_clique.
    conf = comentarios_na_pagina(page, vanity, _trecho(texto))
    if conf.get("com_trecho"):
        return True, "ok", "pos_clique"
    return False, "comentario nao confirmado na pagina", "pos_clique"


# ----------------------------------------------------------------------------
# O navegador
# ----------------------------------------------------------------------------
LOGIN_URL_MARCAS = ("/login", "/uas/login", "/authwall", "/checkpoint/")
RX_CAPTCHA = re.compile(r"unusual activity|security (verification|check)|are you a human|captcha|"
                        r"atividade incomum|verifique sua identidade|verificação de segurança", re.I)
RX_LIMIT = re.compile(r"reached the (weekly )?limit|you('| a)re using.*too|limite (semanal )?atingido|"
                      r"atingiu o limite", re.I)
RX_URL_BLOQUEIO = re.compile(r"linkedin\.com/(checkpoint|challenge)", re.I)
RX_URL_LOGIN = re.compile(r"linkedin\.com/(authwall|uas/login|login)", re.I)
RX_IFRAME_DESAFIO = re.compile(r"recaptcha/.*bframe|arkoselabs|funcaptcha|hcaptcha", re.I)

BLOQUEIO_JS = """() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const chat = el => !!el.closest('[class*="msg-overlay"]');
  const dialogos = [...document.querySelectorAll('[role="dialog"],.artdeco-modal')]
    .filter(e => vis(e) && !chat(e));
  const alertas = [...document.querySelectorAll('[role="alertdialog"],[role="alert"],.artdeco-toast-item')]
    .filter(vis);
  return {
    url: location.href,
    tem_main: !!document.querySelector('main'),
    avisos: [...dialogos, ...alertas].map(e => e.innerText || ''),
    desafios: [...document.querySelectorAll('iframe')]
      .filter(f => { const r = f.getBoundingClientRect(); return r.width > 150 && r.height > 150; })
      .map(f => f.src || ''),
    body: document.body ? (document.body.innerText || '') : '',
  };
}"""


def classificar_bloqueio(d):
    """'SESSAO' | 'CAPTCHA' | 'LIMIT' | None a partir do que o BLOQUEIO_JS leu da página. Puro (testado).
    A tela de login é sessão caída (pede login), não captcha (pararia a rede à toa)."""
    if not isinstance(d, dict):
        return None
    if RX_URL_LOGIN.search(d.get("url") or ""):
        return "SESSAO"
    if RX_URL_BLOQUEIO.search(d.get("url") or ""):
        return "CAPTCHA"
    if any(RX_IFRAME_DESAFIO.search(s or "") for s in d.get("desafios") or []):
        return "CAPTCHA"
    textos = list(d.get("avisos") or [])
    if not d.get("tem_main") and not any(t.strip() for t in textos):
        textos.append(d.get("body") or "")
    if any(RX_CAPTCHA.search(t) for t in textos):
        return "CAPTCHA"
    if any(RX_LIMIT.search(t) for t in textos):
        return "LIMIT"
    return None


def bloqueio(page):
    try:
        return classificar_bloqueio(page.evaluate(BLOQUEIO_JS))
    except Exception:  # noqa: BLE001
        return None


NAVEGADORES = (r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
               r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
               r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
               r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
               r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
               r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe",
               "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
               "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")


def navegador_do_pc():
    """O Chrome ou, sem ele, o Brave instalado no PC (None: só o Chromium do Playwright). O login e o
    robô usam sempre o mesmo, para a sessão salva valer nos dois."""
    return next((p for p in map(os.path.expandvars, NAVEGADORES) if os.path.exists(p)), None)


def dono_do_perfil(perfil_dir):
    """Mac: o pid do Chrome deste computador que está com a pasta aberta, ou None (trava velha de um
    Chrome que caiu não conta)."""
    try:
        host, _, pid = os.readlink(Path(perfil_dir) / "SingletonLock").rpartition("-")  # "<computador>-<pid>"
        if host != socket.gethostname() or not pid.isdigit():
            return None
        nome = subprocess.run(["ps", "-p", pid, "-o", "comm="], capture_output=True, text=True).stdout
    except OSError:
        return None
    return int(pid) if re.search(r"chrom|brave", nome, re.I) else None   # pid reaproveitado: não é dele


def soltar_perfil(perfil_dir, espera_seg=20):
    """No Mac, fechar a janela não fecha o Chrome. Um Chrome esquecido com a pasta da sessão, aberto sem
    a porta (pelas versões até 29/10), engoliria o novo: este só viraria uma aba nele. Pede para ele
    sair (SIGTERM: o Chrome sai como no Cmd+Q e grava os cookies) e espera soltar a pasta. No Windows
    o Chrome fecha com a janela: nada a fazer. True se havia um para fechar."""
    if os.name == "nt":
        return False
    pid = dono_do_perfil(perfil_dir)
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    for _ in range(espera_seg):
        if not os.path.lexists(Path(perfil_dir) / "SingletonLock"):
            break
        time.sleep(1)
    return True


def perfil_em_uso(perfil_dir, espera_seg=15):
    """Um Chrome está com a pasta aberta. Abrir outro com a mesma pasta só manda uma aba nova para ele:
    a cada tentativa do robô, mais uma aba na janela da pessoa. Então não abre. Espera um pouco antes
    de decidir: o Chrome solta a pasta uns segundos depois de fechar."""
    for _ in range(espera_seg * 2):
        if os.name == "nt":
            try:
                (Path(perfil_dir) / "lockfile").unlink(missing_ok=True)   # o Chrome segura este arquivo
                return False
            except OSError:
                pass
        elif dono_do_perfil(perfil_dir) is None:
            return False
        time.sleep(0.5)
    return True


# --------------------------------------------------------------------------------------------
# O Chrome do Replai: o Chrome do PC com uma pasta só dele, aberto como qualquer Chrome, sem as opções
# que o Playwright põe ao abrir um navegador (--no-sandbox, chave falsa de cookies, extensões
# desligadas). A pessoa loga nele numa janela comum, SEM a porta de depuração: com a porta o Chrome se
# declara automatizado (navigator.webdriver, medido em 29/10) e o Google recusa o login. O robô abre o
# mesmo Chrome, na mesma pasta, COM a porta (só no próprio PC) e trabalha por ela. O Chrome não aceita
# a porta no perfil de todo dia (desde a versão 136): por isso a pasta.
# --------------------------------------------------------------------------------------------
class ErroNavegador(Exception):
    pass


ABRIR_SEG = 30


def comando_chrome(exe, perfil_dir, urls=(), fora_da_tela=False, porta=True):
    """A pasta, a porta do robô (o Chrome escolhe e grava em DevToolsActivePort) e o que ele precisa
    para seguir trabalhando com a janela atrás de outras, numa área escondida ou com a tela bloqueada."""
    return [exe, f"--user-data-dir={perfil_dir}", *(["--remote-debugging-port=0"] if porta else []),
            "--no-first-run", "--no-default-browser-check", "--window-size=1280,960",
            "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
            *(["--window-position=-2400,-2400"] if fora_da_tela else []), *(urls or ["about:blank"])]


def escondido_no_mac(cmd, mac=sys.platform == "darwin"):
    """No Mac não há área de trabalho escondida, e o macOS traz de volta a janela posta fora da tela.
    Para o vigia (que roda sozinho a cada poucos minutos) não roubar o foco, o Chrome abre com o app
    escondido, como no Cmd+H (`open -g -j`). Minimizar não serve: janela minimizada para de desenhar e
    os cliques do robô travam. REPLAI_VISIVEL=1 mostra a janela."""
    app = re.match(r"(.+?\.app)/", cmd[0] or "")
    if not mac or not app or os.environ.get("REPLAI_VISIVEL"):
        return cmd
    return ["open", "-n", "-g", "-j", "-a", app.group(1), "--args", *cmd[1:]]


def porta_aberta(perfil_dir):
    """A porta do Chrome do Replai aberto com esta pasta, ou None."""
    import urllib.request
    try:
        porta = int((Path(perfil_dir) / "DevToolsActivePort").read_text().split()[0])
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/version", timeout=3):
            return porta
    except (OSError, ValueError, IndexError):
        return None


def abrir_chrome(perfil_dir, urls=(), fora_da_tela=False, exe=None, porta=True):
    """Abre o Chrome do Replai: (porta, processo). Sem `porta` (o login), não espera nada: (None, processo)."""
    perfil_dir = Path(perfil_dir)
    perfil_dir.mkdir(parents=True, exist_ok=True)
    soltar_perfil(perfil_dir)
    if perfil_em_uso(perfil_dir):
        raise ErroNavegador("uma janela do Chrome do Replai está aberta (talvez a do login). Feche essa "
                            "janela (no Mac, Cmd+Q) e repita")
    (perfil_dir / "DevToolsActivePort").unlink(missing_ok=True)
    cmd = comando_chrome(exe or navegador_do_pc(), perfil_dir, urls, fora_da_tela, porta)
    if fora_da_tela:
        cmd = escondido_no_mac(cmd)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)   # a saída é o JSON
    except (OSError, TypeError) as e:
        raise ErroNavegador(f"não achei o Chrome para abrir ({e}): rode o instalador do Replai")
    if not porta:
        return None, proc
    for _ in range(ABRIR_SEG * 2):
        porta = porta_aberta(perfil_dir)
        if porta:
            return porta, proc
        time.sleep(0.5)
    if proc.poll() is None:
        proc.terminate()
    raise ErroNavegador("o Chrome do Replai não abriu em 30 segundos")


def fechar_chrome(browser, proc=None, espera_seg=20):
    """Fecha o Chrome inteiro como quem fecha a janela (ele grava os cookies) e espera sair."""
    try:
        browser.new_browser_cdp_session().send("Browser.close")
    except Exception:  # noqa: BLE001  (a conexão cai junto com o Chrome)
        pass
    if proc is not None:
        try:
            proc.wait(timeout=espera_seg)
        except subprocess.TimeoutExpired:
            proc.terminate()


def fechar_aberto(pw, perfil_dir, proc=None, espera_seg=20):
    """Fecha o Chrome do Replai desta pasta, se estiver aberto, e espera a porta sumir."""
    porta = porta_aberta(perfil_dir)
    if porta:
        try:
            fechar_chrome(pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}"), proc, espera_seg)
        except Exception:  # noqa: BLE001
            pass
    for _ in range(espera_seg * 2):
        if not porta_aberta(perfil_dir):
            return
        time.sleep(0.5)


class ChromeDoReplai:
    """O que o robô usa do navegador: as abas dele (`pages`, `new_page`) e `close`. O Chrome que o robô
    abriu, ele fecha no fim; um que já estava aberto com a porta (de uma rodada que caiu no meio), o
    robô usa em abas novas, fecha só as dele e deixa o resto como estava."""

    def __init__(self, browser, proc=None):
        self.browser, self.proc = browser, proc
        self.contexto = browser.contexts[0]
        self.pages = list(self.contexto.pages) if proc else []      # a aba com que ele abriu é do robô

    def new_page(self):
        page = self.contexto.new_page()
        self.pages.append(page)
        return page

    def close(self):
        if self.proc is not None:
            return fechar_chrome(self.browser, self.proc)
        for page in self.pages:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass
        self.browser.close()                                        # só solta a conexão


def abrir_contexto(pw, perfil_dir, fora_da_tela=False):
    """O Chrome do Replai com a sessão salva em `perfil_dir`, para as duas redes (visível: as redes
    desconfiam de headless). `fora_da_tela` põe a janela fora da área visível, para o vigia não
    atrapalhar quem está usando o PC."""
    porta, proc = porta_aberta(perfil_dir), None
    if not porta:
        porta, proc = abrir_chrome(perfil_dir, fora_da_tela=fora_da_tela,
                                   exe=navegador_do_pc() or pw.chromium.executable_path)
    try:
        return ChromeDoReplai(pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}"), proc)
    except Exception as e:  # noqa: BLE001
        if proc is not None:
            proc.terminate()
        raise ErroNavegador(f"não consegui falar com o Chrome do Replai: {e}")


def sessao_expirada(page):
    try:
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
    except Exception:  # noqa: BLE001
        return False
    url = (page.url or "").lower()
    if any(m in url for m in LOGIN_URL_MARCAS):
        return True
    try:
        return bool(page.query_selector('input[name="session_key"]'))
    except Exception:  # noqa: BLE001
        return False


# Comentários recentes da PRÓPRIA conta (amostra para a voz). A MEDIR na tela real (Task 12): se vier
# vazio com a conta tendo comentado, o seletor mudou e a voz sai só dos posts e da entrevista.
JS_COMENTARIOS_PROPRIOS = r"""
([vanity]) => {
  const norm = s => (s || '').toLowerCase();
  const alvo = '/in/' + norm(vanity);
  const itens = [...document.querySelectorAll('article.comments-comment-entity, .comments-comment-item, [data-id^="urn:li:comment"], ' +
                                              '[componentkey^="replaceableComment_urn:li:comment"]')];
  const out = [];
  for (const it of itens) {
    const meu = [...it.querySelectorAll('a[href*="/in/"]')]
      .some(a => norm(decodeURIComponent(a.getAttribute('href') || '')).includes(alvo));
    if (!meu) continue;
    const corpo = it.querySelector('.comments-comment-item__main-content, .comments-comment-entity__content, .update-components-text, ' +
                                   '[data-testid="expandable-text-box"]');
    const t = (corpo ? corpo.innerText : '').trim();
    if (t) out.push(t);
  }
  return JSON.stringify(out);
}
"""


def comentarios_proprios(page, vanity, rolagens=4):
    page.goto(f"https://www.linkedin.com/in/{vanity}/recent-activity/comments/",
              wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    for _ in range(rolagens):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(2000)
    r = _json(page, JS_COMENTARIOS_PROPRIOS, [vanity or ""])
    vistos, out = set(), []
    for t in r if isinstance(r, list) else []:
        if t not in vistos:
            vistos.add(t)
            out.append(t)
    return out


# ----------------------------------------------------------------------------
# Vigia do LinkedIn: o sininho de cada perfil da lista e a página de notificações.
# A MEDIR na tela real: o botão do sininho e o desenho dos avisos. O `calibrar` mostra o que foi achado.
# ----------------------------------------------------------------------------
URL_NOTIFICACOES = "https://www.linkedin.com/notifications/?filter=all"

# Cada aviso que aponta para um post (link com o id da activity) e o perfil de quem aparece nele. Aviso
# de "fulano comentou no post de ciclano" também casa, mas a coleta só aceita o id que estiver entre os
# posts do próprio fulano: o resto cai sozinho.
JS_NOTIFICACOES = r"""
() => {
  const saida = [], vistos = new Set();
  const links = [...document.querySelectorAll('a[href*="activity"], a[href*="/feed/update/"]')];
  for (const a of links) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/urn(?::|%3A)li(?::|%3A)activity(?::|%3A)(\d{10,25})/i);
    if (!m) continue;
    const card = a.closest('article, li, [data-finite-scroll-hotkey-item], [class*="nt-card"], [class*="notification"]')
      || a.parentElement;
    const perfil = card ? card.querySelector('a[href*="/in/"]') : null;
    const pm = perfil ? (perfil.getAttribute('href') || '').match(/\/in\/([^/?#]+)/) : null;
    if (!pm) continue;
    const vanity = decodeURIComponent(pm[1]).toLowerCase();
    if (vistos.has(vanity + ' ' + m[1])) continue;
    vistos.add(vanity + ' ' + m[1]);
    saida.push({ vanity: vanity, activity: m[1], texto: (card.innerText || '').replace(/\s+/g, ' ').slice(0, 160) });
  }
  return JSON.stringify(saida);
}
"""


def posts_das_notificacoes(page, rolagens=2):
    """[{vanity, activity, texto}] dos avisos visíveis na página de notificações."""
    page.goto(URL_NOTIFICACOES, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    for _ in range(rolagens):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(2000)
    r = _json(page, JS_NOTIFICACOES, [])
    return r if isinstance(r, list) else []


# O sininho do topo do perfil ("avisar todas as publicações"). Ligado = aria-pressed ou rótulo de
# desligar. Fica marcado com data-replai="sino"; a opção "todas as publicações", quando o LinkedIn abre
# um menu depois do clique, com data-replai="todas". `botoes` volta para o calibrar.
JS_SININHO = r"""
() => {
  const norm = s => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  document.querySelectorAll('[data-replai]').forEach(e => e.removeAttribute('data-replai'));
  const topo = document.querySelector('main section') || document.querySelector('main');
  if (!topo) return JSON.stringify({ achou_perfil: false });
  const rot = b => norm((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || ''));
  const RX_SINO = /notifica|notif|bell|sino|alert|all (of )?.{0,40}posts|todas as (suas )?publica/;
  const botoes = [...topo.querySelectorAll('button')].filter(vis);
  const sino = botoes.find(b => RX_SINO.test(rot(b)));
  if (sino) sino.setAttribute('data-replai', 'sino');
  const ligado = sino ? (sino.getAttribute('aria-pressed') === 'true' || /turn off|desativar|desligar|stop|parar/.test(rot(sino))) : null;
  const RX_TODAS = /all posts|todas as publica|todos os posts|todas las publica/;
  const opcoes = [...document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="radio"], [role="option"], label, li')]
    .filter(e => vis(e) && RX_TODAS.test(norm(e.innerText)));
  if (opcoes[0]) opcoes[0].setAttribute('data-replai', 'todas');
  return JSON.stringify({ achou_perfil: true, achou_sino: !!sino, ligado: ligado,
                          rotulo: sino ? rot(sino).slice(0, 80) : null, menu_todas: !!opcoes[0],
                          botoes: botoes.map(rot).slice(0, 12) });
}
"""


def sininho(page):
    return _json(page, JS_SININHO, [])


def ligar_sininho(page, perfil_url):
    """(situação, detalhe), com situação 'ligado' | 'ja_estava' | 'sem_botao' | 'nao_confirmou' |
    'CAPTCHA' | 'LIMIT'. Só clica no sininho DESLIGADO (clicar no ligado desligaria)."""
    page.goto(perfil_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4500)
    b = bloqueio(page)
    if b:
        return b, "a rede deu sinal no perfil"
    s = sininho(page)
    if not s.get("achou_perfil"):
        return "sem_botao", "o perfil não abriu"
    if not s.get("achou_sino"):
        return "sem_botao", "sininho não achado (botões: " + ", ".join(s.get("botoes") or [])[:160] + ")"
    if s.get("ligado"):
        return "ja_estava", s.get("rotulo") or ""
    try:
        page.locator('[data-replai="sino"]').first.click(timeout=5000)
    except Exception as e:  # noqa: BLE001
        return "sem_botao", f"clique no sininho falhou ({type(e).__name__})"
    page.wait_for_timeout(2000)
    depois = sininho(page)
    if depois.get("menu_todas"):
        try:
            page.locator('[data-replai="todas"]').first.click(timeout=5000)
            page.wait_for_timeout(2000)
        except Exception:  # noqa: BLE001
            pass
        depois = sininho(page)
    if depois.get("ligado"):
        return "ligado", depois.get("rotulo") or ""
    return "nao_confirmou", depois.get("rotulo") or "sem rótulo depois do clique"
