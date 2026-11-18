#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Replai · X: leitura pelo que o próprio x.com carrega (GraphQL capturado) e curtir/responder na tela.
"""O X não tem API grátis: o Replai lê o que a página da conta já baixa e clica como gente.

LEITURA. As páginas da Lista, da busca, do perfil e do post chamam a API GraphQL interna do X; o
`Leitor` guarda essas respostas enquanto a página carrega e os parsers daqui acham os tweets nelas. O
nome da operação (ListLatestTweetsTimeline, ListMembers, SearchTimeline, UserTweets,
UserTweetsAndReplies) está na URL; o `queryId`, que o X troca, não importa. Os parsers procuram o
objeto do tweet em qualquer profundidade, porque o X muda o embrulho com frequência: tweet sem algum
campo entra com o campo vazio em vez de quebrar a rodada.

ESCRITA. Curtir e responder são cliques reais na tela, pela mesma razão do LinkedIn: a escrita é o
que a rede vigia, e ela tem de parecer o que é, uma pessoa usando o site.

A MEDIR na tela real (última task da fase 2): os data-testid e o formato de cada operação. O
`calibrar` mostra o que foi achado.
"""
import json
import random
import re
import time
from datetime import datetime
from urllib.parse import quote

BUSCA_MAX_HANDLES = 15


def _obj(v):
    return isinstance(v, dict)


def percorrer(v, visitar, prof=0):
    """Visita todo dict (inclusive dentro de listas), em profundidade."""
    if prof > 60:
        return
    if isinstance(v, list):
        for x in v:
            percorrer(x, visitar, prof + 1)
    elif _obj(v):
        visitar(v)
        for x in v.values():
            percorrer(x, visitar, prof + 1)


# ----------------------------------------------------------------------------
# Parsers (puros, testados com respostas sintéticas no formato do X)
# ----------------------------------------------------------------------------
def data_x(s):
    """'Wed Oct 10 20:19:24 +0000 2018' -> ISO com fuso, ou None."""
    try:
        return datetime.strptime(s or "", "%a %b %d %H:%M:%S %z %Y").isoformat()
    except ValueError:
        return None


def usuario(u):
    """(handle, nome, bio) de um objeto User (formato novo, com `core`, ou antigo, só `legacy`)."""
    if not _obj(u):
        return "", "", ""
    core = u.get("core") if _obj(u.get("core")) else {}
    leg = u.get("legacy") if _obj(u.get("legacy")) else {}
    bio = leg.get("description") or ((u.get("profile_bio") or {}).get("description")
                                     if _obj(u.get("profile_bio")) else "") or ""
    return core.get("screen_name") or leg.get("screen_name") or "", core.get("name") or leg.get("name") or "", bio


def _desembrulhar(o):
    if o.get("__typename") == "TweetWithVisibilityResults" and _obj(o.get("tweet")):
        return o["tweet"]
    return o


def _id_de(o):
    if not _obj(o):
        return None
    o = _desembrulhar(o)
    leg = o.get("legacy") if _obj(o.get("legacy")) else {}
    return str(o.get("rest_id") or leg.get("id_str") or "") or None


def ler_tweet(o):
    """Um objeto Tweet do GraphQL -> dict, ou None se não for tweet (User também tem rest_id e legacy,
    mas não tem full_text)."""
    o = _desembrulhar(o)
    leg = o.get("legacy")
    if o.get("__typename") == "User" or not _obj(leg) or "full_text" not in leg:
        return None
    pid = _id_de(o)
    if not pid:
        return None
    u = ((o.get("core") or {}).get("user_results") or {}).get("result") if _obj(o.get("core")) else None
    handle, nome, bio = usuario(u)
    nota = o.get("note_tweet") if _obj(o.get("note_tweet")) else {}
    nota = ((nota.get("note_tweet_results") or {}).get("result") or {}) if nota else {}
    rt = (leg.get("retweeted_status_result") or {}).get("result") if _obj(leg.get("retweeted_status_result")) else None
    return {"id": pid, "texto": nota.get("text") or leg.get("full_text") or "",
            "data": data_x(leg.get("created_at")), "idioma": leg.get("lang") or "",
            "autor": handle.lower(), "nome": nome, "bio": (bio or "")[:120],
            "n_curtidas": leg.get("favorite_count"), "n_comentarios": leg.get("reply_count"),
            "curtido": bool(leg.get("favorited")),
            "resposta_a": leg.get("in_reply_to_status_id_str") or None,
            "retweet_de": _id_de(rt), "citacao_de": leg.get("quoted_status_id_str") or None,
            "url": f"https://x.com/{handle or 'i'}/status/{pid}"}


def tweets_da_resposta(raw):
    """Todos os tweets de uma resposta GraphQL (inclusive os citados e retuitados, que aparecem
    aninhados), sem repetir id, na ordem em que aparecem."""
    vistos, saida = set(), []

    def visitar(o):
        if o.get("__typename") in ("Tweet", "TweetWithVisibilityResults") or (
                "rest_id" in o and _obj(o.get("legacy"))):
            t = ler_tweet(o)
            if t and t["id"] not in vistos:
                vistos.add(t["id"])
                saida.append(t)
    percorrer(raw, visitar)
    return saida


def membros_da_resposta(raw):
    """Handles (minúsculos) dos membros numa resposta ListMembers. Olha só dentro de
    `members_timeline` quando ele existe: o dono da Lista também vem na resposta."""
    base = []
    percorrer(raw, lambda o: base.append(o["members_timeline"]) if "members_timeline" in o else None)
    saida = []

    def visitar(o):
        if o.get("__typename") == "User":
            h = usuario(o)[0].lower()
            if h and h not in saida:
                saida.append(h)
    percorrer(base[0] if base else raw, visitar)
    return saida


def autores_de_topo(tweets):
    """Quem postou no feed (fora os tweets que só aparecem por estarem citados ou retuitados). É a
    lista de membros quando a página de membros não pôde ser lida."""
    refs = {t.get("retweet_de") for t in tweets} | {t.get("citacao_de") for t in tweets}
    return {t["autor"] for t in tweets if t["id"] not in refs and t["autor"]}


def respondidos(tweets, meu):
    """{id do post respondido: data da resposta} das respostas da conta (aba de respostas do perfil)."""
    h = (meu or "").lower()
    return {t["resposta_a"]: t.get("data") for t in tweets if t["autor"] == h and t.get("resposta_a")}


def consultas_de_busca(handles, n=BUSCA_MAX_HANDLES):
    """'(from:a OR from:b ...)' em lotes de até n: uma página de busca cobre o lote inteiro."""
    hs = [h.lower() for h in handles if h]
    return ["(" + " OR ".join(f"from:{h}" for h in hs[i:i + n]) + ")" for i in range(0, len(hs), n)]


# ----------------------------------------------------------------------------
# Bloqueio (puro + o JS que lê a tela)
# ----------------------------------------------------------------------------
RX_BLOQ_TEXTO = re.compile(
    r"rate limit|temporarily (limited|restricted)|your account (is|has been) (locked|suspended)|"
    r"unusual activity|are you a robot|conta (foi )?(bloqueada|suspensa)|temporariamente limitad|"
    r"atividade incomum|limite de (taxa|requisi)", re.I)
RX_DESAFIO = re.compile(r"arkoselabs|funcaptcha|recaptcha|hcaptcha", re.I)

BLOQUEIO_JS = """() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const avisos = [...document.querySelectorAll('[role="alertdialog"],[role="alert"],[data-testid="toast"],[data-testid="sheetDialog"]')]
    .filter(vis).map(e => e.innerText || '');
  return {
    url: location.href,
    tem_main: !!document.querySelector('main[role="main"], [data-testid="primaryColumn"]'),
    avisos: avisos,
    desafios: [...document.querySelectorAll('iframe')]
      .filter(f => { const r = f.getBoundingClientRect(); return r.width > 150 && r.height > 150; })
      .map(f => f.src || ''),
    body: document.body ? (document.body.innerText || '').slice(0, 3000) : '',
  };
}"""


def classificar_bloqueio(d):
    """'SESSAO' (deslogado), 'BLOQUEIO' (conta travada), 'CAPTCHA', 'LIMIT' ou None. Puro (testado)."""
    if not _obj(d):
        return None
    url = d.get("url") or ""
    if re.search(r"(x|twitter)\.com/account/access", url):
        return "BLOQUEIO"
    if re.search(r"(x|twitter)\.com/(i/flow/login|login|logout)", url):
        return "SESSAO"
    if any(RX_DESAFIO.search(s or "") for s in d.get("desafios") or []):
        return "CAPTCHA"
    textos = list(d.get("avisos") or [])
    if not d.get("tem_main"):
        textos.append(d.get("body") or "")
    if any(RX_BLOQ_TEXTO.search(t or "") for t in textos):
        return "LIMIT"
    return None


def bloqueio(page):
    try:
        return classificar_bloqueio(page.evaluate(BLOQUEIO_JS))
    except Exception:  # noqa: BLE001
        return None


class ErroX(Exception):
    def __init__(self, tipo, msg):
        super().__init__(msg)
        self.tipo = tipo


# ----------------------------------------------------------------------------
# O leitor: abre páginas e guarda o GraphQL que elas baixam
# ----------------------------------------------------------------------------
JS_ME = """() => { const a = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
  return a ? (a.getAttribute('href') || '').replace(/^\\//, '') : ''; }"""


class Leitor:
    """Uma página por vez, com pausa entre elas; `ao_ler(tipo)` é chamado a cada página aberta (o
    registro conta no teto do dia). Bloqueio na tela levanta ErroX."""

    def __init__(self, page, ao_ler=None, pausa=(4, 9), rng=None, dormir=time.sleep):
        self.page, self.ao_ler, self.pausa = page, ao_ler, pausa
        self.rng = rng or random.Random()
        self.dormir = dormir
        self.feitas = 0
        self._respostas = []
        page.on("response", self._guardar)

    def _guardar(self, resp):
        try:
            if "/graphql/" in resp.url:
                self._respostas.append(resp)
        except Exception:  # noqa: BLE001
            pass

    def _abrir(self, url, ops, rolagens=1, tipo="pagina"):
        if self.feitas:
            self.dormir(self.rng.uniform(*self.pausa))
        self._respostas.clear()
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self.page.wait_for_timeout(4500)
        for _ in range(rolagens):
            self.page.mouse.wheel(0, 2200)
            self.page.wait_for_timeout(2000)
        self.feitas += 1
        if self.ao_ler:
            self.ao_ler(tipo)
        b = bloqueio(self.page)
        if b:
            raise ErroX(b, f"{b} no X em {url}")
        nome = lambda r: r.url.split("?")[0].rsplit("/", 1)[-1]  # noqa: E731
        escolhidas = [r for r in self._respostas if nome(r) in ops]
        if not escolhidas:      # o X renomeia as operações (27/10/2026: UserTweets virou UserOriginalsTimeline)
            escolhidas = [r for r in self._respostas if nome(r).endswith("Timeline")]
        dados = []
        for r in escolhidas:
            try:
                dados.append(r.json())
            except Exception:  # noqa: BLE001
                continue
        return dados

    def _tweets(self, dados):
        vistos, saida = set(), []
        for d in dados:
            for t in tweets_da_resposta(d):
                if t["id"] not in vistos:
                    vistos.add(t["id"])
                    saida.append(t)
        return saida

    def me(self):
        """O @ da conta logada (sem @), ou '' se não deu para ler. Aproveita a home já aberta pela
        conferência de sessão (cada página a menos conta, com o vigia a cada 10 min)."""
        if "x.com/home" not in (self.page.url or ""):
            self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        meu = _esperar_conta(self.page)
        b = bloqueio(self.page)
        if b:
            raise ErroX(b, f"{b} no X ao abrir a home")
        return meu

    def lista(self, url):
        return self._tweets(self._abrir(url, ("ListLatestTweetsTimeline",), rolagens=2, tipo="lista"))

    def membros(self, url):
        dados = self._abrir(url.rstrip("/") + "/members", ("ListMembers",), rolagens=3, tipo="membros")
        saida = []
        for d in dados:
            saida += [h for h in membros_da_resposta(d) if h not in saida]
        return saida

    def busca(self, handles):
        tweets = []
        for q in consultas_de_busca(handles):
            url = f"https://x.com/search?q={quote(q)}&src=typed_query&f=live"
            tweets += self._tweets(self._abrir(url, ("SearchTimeline",), rolagens=1, tipo="busca"))
        return tweets

    def perfil(self, handle):
        return self._tweets(self._abrir(f"https://x.com/{handle}", ("UserTweets", "UserOriginalsTimeline"),
                                        rolagens=2, tipo="perfil"))

    def respostas_da_conta(self, meu):
        """As respostas da conta: uma das travas de "nunca responder duas vezes". FAIL-CLOSED: a tela com
        posts e a leitura vazia quer dizer que o X mudou a página, e aí nada segue sem essa trava."""
        tweets = self._tweets(self._abrir(f"https://x.com/{meu}/with_replies",
                                          ("UserTweetsAndReplies", "UserTweets", "UserRepliesTimeline"),
                                          rolagens=2, tipo="respostas"))
        if not tweets and _artigos_na_tela(self.page):
            raise ErroX("LEITURA", "a leitura das respostas da conta veio vazia com a tela cheia: o X mudou "
                                   "a página (rode 'testar' e avise quem mantém o Replai)")
        return tweets


def _artigos_na_tela(page):
    try:
        return page.evaluate("document.querySelectorAll('article').length") or 0
    except Exception:  # noqa: BLE001
        return 0


def _logado_pelo_cookie(page):
    """O X grava o cookie auth_token quando a conta está logada: é a prova mais estável (não depende
    do desenho da página nem de ela ter terminado de carregar)."""
    try:
        return any(c.get("name") == "auth_token" and c.get("value")
                   for c in page.context.cookies("https://x.com"))
    except Exception:  # noqa: BLE001
        return False


def _esperar_conta(page, ms=20000):
    """O @ da conta pelo link "Perfil" da barra lateral, esperando o X carregar (até `ms`)."""
    try:
        page.wait_for_selector('a[data-testid="AppTabBar_Profile_Link"]', timeout=ms)
    except Exception:  # noqa: BLE001
        pass
    try:
        return (page.evaluate(JS_ME) or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def sessao_expirada(page):
    """True só com prova: o X mandou para o login, ou não há cookie de login nem conta na página.
    (Antes eram 4 s fixos: com o X lento, a conta logada parecia deslogada e o login era pedido de novo.)"""
    try:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
    except Exception:  # noqa: BLE001
        return False
    if classificar_bloqueio({"url": page.url or "", "tem_main": True}) == "SESSAO":
        return True
    if _logado_pelo_cookie(page):
        return False
    return not _esperar_conta(page)


# ----------------------------------------------------------------------------
# A tela do post (as únicas linhas que conhecem o DOM do X; se ele mudar, o ajuste é aqui)
# ----------------------------------------------------------------------------
# Mesmo contrato do linkedin.controles: marca os controles DESTE post com data-replai. O post é o
# <article> cujo link de horário termina em /status/<id> (o citado dentro dele não tem esse link).
JS_CONTROLES = r"""
([id]) => {
  document.querySelectorAll('[data-replai]').forEach(e => e.removeAttribute('data-replai'));
  const limpo = h => (h || '').split('?')[0].replace(/\/(photo|video|analytics|history)\/?.*$/, '');
  const arts = [...document.querySelectorAll('article')];
  const doPost = arts.find(a => [...a.querySelectorAll('a[href*="/status/"]')]
      .some(l => limpo(l.getAttribute('href')).endsWith('/status/' + id) && l.querySelector('time')));
  if (!doPost) return JSON.stringify({ achou_post: false, tem_algum_post: arts.length > 0 });
  const like = doPost.querySelector('[data-testid="like"]');
  const unlike = doPost.querySelector('[data-testid="unlike"]');
  const caixa = document.querySelector('[data-testid="tweetTextarea_0"]');
  const enviar = document.querySelector('[data-testid="tweetButtonInline"]');
  if (like) like.setAttribute('data-replai', 'like');
  if (caixa) caixa.setAttribute('data-replai', 'editor');
  if (enviar) enviar.setAttribute('data-replai', 'submit');
  return JSON.stringify({
    achou_post: true,
    like: { achou: !!(like || unlike), pressionado: unlike ? 'true' : (like ? 'false' : null) },
    comentar: { achou: !!doPost.querySelector('[data-testid="reply"]') },
    editor: !!caixa,
    enviar: { achou: !!enviar,
              desabilitado: enviar ? (enviar.disabled || enviar.getAttribute('aria-disabled') === 'true') : null },
  });
}
"""

# As respostas da conta visíveis na página do post: alguma é dela? O trecho do nosso texto apareceu?
JS_RESPOSTAS = r"""
([meu, trecho]) => {
  const norm = s => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();
  const arts = [...document.querySelectorAll('article')];
  const daConta = a => [...a.querySelectorAll('a[href]')].some(l => norm(l.getAttribute('href')) === '/' + norm(meu));
  const minhas = meu ? arts.filter(daConta) : [];
  const t = norm(trecho);
  const comTrecho = t ? minhas.find(a => norm(a.innerText).includes(t)) : null;
  let link = null;
  if (comTrecho) {
    const l = [...comTrecho.querySelectorAll('a[href*="/status/"]')].find(x => x.querySelector('time'));
    link = l ? 'https://x.com' + l.getAttribute('href').split('?')[0] : null;
  }
  return JSON.stringify({ n: arts.length, da_conta: minhas.length > 0, com_trecho: !!comTrecho, link: link });
}
"""


def _json(page, js, args):
    try:
        bruto = page.evaluate(js, args)
        return json.loads(bruto) if isinstance(bruto, str) else (bruto or {})
    except Exception as e:  # noqa: BLE001 - página navegando/fechada: não afirma nada
        return {"erro": f"{type(e).__name__}: {e}"}


def controles(page, tweet_id):
    return _json(page, JS_CONTROLES, [str(tweet_id or "")])


def respostas_na_pagina(page, meu, trecho=""):
    return _json(page, JS_RESPOSTAS, [meu or "", trecho or ""])


def _trecho(texto, n=40):
    return " ".join((texto or "").split())[:n]


def curtir(page, tweet_id):
    """(ok, motivo, fase). Só clica no coração NÃO marcado (clicar no marcado descurte)."""
    c = controles(page, tweet_id)
    estado = (c.get("like") or {}).get("pressionado")
    if not (c.get("like") or {}).get("achou"):
        return False, "botão de curtir não achado", "pre_clique"
    if estado == "true":
        return False, "já curtido (clicar de novo descurtiria)", "pre_clique"
    if estado != "false":
        return False, f"estado da curtida desconhecido ({estado!r}): não clico", "pre_clique"
    try:
        page.locator('[data-replai="like"]').first.click(timeout=5000)
    except Exception as e:  # noqa: BLE001 - o clique pode ter saído antes da exceção: INCERTO
        return False, f"clique de curtir deu exceção ({type(e).__name__}); pode ter saído", "pos_clique"
    page.wait_for_timeout(1500)
    if (controles(page, tweet_id).get("like") or {}).get("pressionado") == "true":
        return True, "ok", "pos_clique"
    return False, "curtida não confirmada (o coração não virou)", "pos_clique"


def comentar(page, tweet_id, texto, meu, rng=random):
    """Responde pela caixa da própria página do post. (ok, motivo, fase). FAIL-CLOSED: sem caixa, sem
    botão ou botão desabilitado, nada sai. Confirma pelo trecho numa resposta da conta na página."""
    c = controles(page, tweet_id)
    if not c.get("achou_post"):
        return False, "post não achado na página", "pre_clique"
    if not c.get("editor"):
        return False, "caixa de resposta não apareceu (respostas restritas?)", "pre_clique"
    try:
        page.locator('[data-replai="editor"]').first.click(timeout=5000)
        page.wait_for_timeout(500)
        page.keyboard.type(texto, delay=int(rng.uniform(25, 55)))
    except Exception as e:  # noqa: BLE001
        return False, f"digitação falhou ({type(e).__name__})", "pre_clique"
    page.wait_for_timeout(1200)
    env = controles(page, tweet_id).get("enviar") or {}
    if not env.get("achou"):
        return False, "botão de responder não achado", "pre_clique"
    if env.get("desabilitado"):
        return False, "botão de responder DESABILITADO", "pre_clique"
    try:
        page.locator('[data-replai="submit"]').first.click(timeout=5000)
    except Exception as e:  # noqa: BLE001
        return False, f"clique em responder deu exceção ({type(e).__name__}); pode ter saído", "pos_clique"
    page.wait_for_timeout(4500)
    if respostas_na_pagina(page, meu, _trecho(texto)).get("com_trecho"):
        return True, "ok", "pos_clique"
    return False, "resposta não confirmada na página", "pos_clique"
