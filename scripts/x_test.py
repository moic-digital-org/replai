#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Replai · testes PUROS do x.py (parsers e bloqueio) com respostas sintéticas no formato do X.
"""Rodar:  python x_test.py

As respostas reais gravadas na tela (última task da fase 2) entram aqui como fixtures depois, com os
nomes trocados."""
import sys

import x as X

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

_ok = _fail = 0


def check(cond, label):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  [OK ] {label}")
    else:
        _fail += 1
        print(f"  [FAIL] {label}")


def user(handle, nome, novo=True, bio="Payments at Acme"):
    u = {"__typename": "User", "rest_id": "u-" + handle, "legacy": {"description": bio, "created_at": "Tue Mar 21 20:50:14 +0000 2006"}}
    if novo:
        u["core"] = {"screen_name": handle, "name": nome}
    else:
        u["legacy"].update(screen_name=handle, name=nome)
    return u


def tweet(tid, handle, texto, quando="Wed Nov 04 16:30:00 +0000 2026", novo=True, **leg):
    legacy = {"full_text": texto, "created_at": quando, "lang": leg.pop("lang", "en"), "favorite_count": 12,
              "reply_count": 3, "retweet_count": 1, "favorited": leg.pop("favorited", False), "id_str": tid}
    legacy.update(leg)
    return {"__typename": "Tweet", "rest_id": tid,
            "core": {"user_results": {"result": user(handle, handle.title(), novo)}}, "legacy": legacy}


def entrada(t):
    return {"entryId": "tweet-" + (t.get("rest_id") or t["tweet"]["rest_id"]), "content": {"__typename": "TimelineTimelineItem",
            "itemContent": {"__typename": "TimelineTweet", "tweet_results": {"result": t}}}}


def timeline(*tweets, raiz="list"):
    instrucoes = [{"type": "TimelineAddEntries", "entries": [entrada(t) for t in tweets]}]
    if raiz == "list":
        return {"data": {"list": {"tweets_timeline": {"timeline": {"instructions": instrucoes}}}}}
    return {"data": {"search_by_raw_query": {"search_timeline": {"timeline": {"instructions": instrucoes}}}}}


print("\n== 1. tweets de uma timeline ==")
original = tweet("200", "carol", "Original post by someone outside the list, about settlement rails.")
rt = tweet("201", "ana", "RT @carol: Original post by someone outside the list", retweeted_status_result={"result": original})
quote_ = tweet("202", "bruno", "This is the part nobody talks about: off-ramp liquidity in LatAm.",
               is_quote_status=True, quoted_status_id_str="200")
quote_["quoted_status_result"] = {"result": original}
resposta = tweet("203", "ana", "@dave agreed, the bank side is the bottleneck", in_reply_to_status_id_str="150")
longo = tweet("204", "ana", "Texto cortado no full_text…", novo=False, lang="pt")
longo["note_tweet"] = {"note_tweet_results": {"result": {"text": "Texto inteiro do note tweet, bem maior que 280 caracteres."}}}
visivel = {"__typename": "TweetWithVisibilityResults", "tweet": tweet("205", "bruno", "Wrapped tweet with visibility results, still a normal post.")}
raw = timeline(rt, quote_, resposta, longo, visivel)
ts = X.tweets_da_resposta(raw)
por_id = {t["id"]: t for t in ts}
check(set(por_id) == {"200", "201", "202", "203", "204", "205"}, "acha todos os tweets, inclusive aninhados e embrulhados")
check(por_id["201"]["retweet_de"] == "200" and por_id["201"]["autor"] == "ana", "retweet aponta o original")
check(por_id["202"]["citacao_de"] == "200" and por_id["202"]["retweet_de"] is None, "citação aponta o citado")
check(por_id["203"]["resposta_a"] == "150", "resposta aponta o post respondido")
check(por_id["204"]["texto"].startswith("Texto inteiro") and por_id["204"]["autor"] == "ana" and por_id["204"]["idioma"] == "pt",
      "texto longo (note tweet) e usuário no formato antigo")
check(por_id["205"]["autor"] == "bruno" and por_id["205"]["url"] == "https://x.com/bruno/status/205",
      "TweetWithVisibilityResults é desembrulhado; url do post")
check(por_id["202"]["data"] == "2026-11-04T16:30:00+00:00" and por_id["202"]["n_comentarios"] == 3,
      "data e contagens")
check(por_id["202"]["bio"] == "Payments at Acme", "bio do autor")
check(X.autores_de_topo(ts) == {"ana", "bruno"}, "autores de topo: fora quem só aparece citado ou retuitado")
check(X.tweets_da_resposta({"data": {"user": user("x", "X")}}) == [], "usuário sozinho não vira tweet")

print("\n== 2. membros, respondidos, busca ==")
membros = {"data": {"list": {"user_results": {"result": user("dono", "Dono")},
                             "members_timeline": {"timeline": {"instructions": [{"entries": [
                                 {"content": {"itemContent": {"user_results": {"result": user("Ana", "Ana")}}}},
                                 {"content": {"itemContent": {"user_results": {"result": user("bruno", "Bruno", novo=False)}}}},
                             ]}]}}}}}
check(X.membros_da_resposta(membros) == ["ana", "bruno"], "membros da Lista (sem o dono, em minúsculas)")
minhas = X.tweets_da_resposta(timeline(tweet("300", "lucia", "minha resposta", in_reply_to_status_id_str="202"),
                                       tweet("301", "lucia", "meu post"), resposta))
check(X.respondidos(minhas, "Lucia") == {"202": "2026-11-04T16:30:00+00:00"}, "posts que a conta já respondeu, com a hora da resposta")
qs = X.consultas_de_busca([f"h{i}" for i in range(20)])
check(len(qs) == 2 and qs[0].startswith("(from:h0 OR from:h1") and qs[1] == "(from:h15 OR from:h16 OR from:h17 OR from:h18 OR from:h19)",
      "busca em lotes de 15 @")
check(X.data_x("lixo") is None, "data ilegível")

print("\n== 3. bloqueio ==")
check(X.classificar_bloqueio({"url": "https://x.com/account/access", "tem_main": True}) == "BLOQUEIO", "conta travada")
check(X.classificar_bloqueio({"url": "https://x.com/i/flow/login?redirect=1", "tem_main": True}) == "SESSAO", "deslogado")
check(X.classificar_bloqueio({"url": "https://x.com/home", "tem_main": True,
                              "desafios": ["https://client-api.arkoselabs.com/x"]}) == "CAPTCHA", "desafio")
check(X.classificar_bloqueio({"url": "https://x.com/home", "tem_main": True,
                              "avisos": ["Your account is temporarily limited"]}) == "LIMIT", "aviso de limite")
check(X.classificar_bloqueio({"url": "https://x.com/home", "tem_main": False, "avisos": [],
                              "body": "Rate limit exceeded"}) == "LIMIT", "rate limit sem a tela normal")
check(X.classificar_bloqueio({"url": "https://x.com/home", "tem_main": True, "avisos": ["Your post was sent."]}) is None,
      "aviso normal não é bloqueio")
check(X.classificar_bloqueio(None) is None, "leitura falhou: nada")

print("\n== 4. sessão do X: logado não pode parecer deslogado ==")


class Ctx:
    def __init__(self, cookies):
        self._c = cookies

    def cookies(self, url):
        return self._c


class PaginaX:
    def __init__(self, url_final, cookies=(), handle=""):
        self.url, self._final, self.context, self._h = "", url_final, Ctx(list(cookies)), handle

    def goto(self, url, **kw):
        self.url = self._final

    def wait_for_selector(self, sel, timeout=0):
        if not self._h:
            raise TimeoutError("sem o link do perfil")

    def evaluate(self, js, *a):
        return self._h


check(X.sessao_expirada(PaginaX("https://x.com/home", [{"name": "auth_token", "value": "abc"}])) is False,
      "com o cookie de login, vale mesmo se a página ainda não mostrou a conta (X lento)")
check(X.sessao_expirada(PaginaX("https://x.com/home", [], handle="lucia")) is False, "sem cookie mas com a conta na página: logado")
check(X.sessao_expirada(PaginaX("https://x.com/i/flow/login", [{"name": "auth_token", "value": "abc"}])) is True,
      "o X mandou para o login: deslogado")
check(X.sessao_expirada(PaginaX("https://x.com/home", [])) is True, "sem cookie e sem conta: deslogado")

print("\n== 5. o X renomeia as operações: a leitura acompanha ou para ==")


class RespG:
    def __init__(self, op, dado):
        self.url, self._d = f"https://x.com/i/api/graphql/abc/{op}?variables=1", dado

    def json(self):
        return self._d


class Mouse:
    def wheel(self, *a):
        pass


class PaginaG:
    """Página que, ao abrir uma url, 'recebe' as respostas GraphQL configuradas e mostra N artigos."""
    def __init__(self, por_url, artigos=0):
        self.por_url, self.artigos, self.url, self._cb, self.mouse = por_url, artigos, "", None, Mouse()

    def on(self, ev, cb):
        self._cb = cb

    def goto(self, url, **kw):
        self.url = url
        for r in self.por_url.get(url, []):
            self._cb(r)

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, js, *a):
        if "article" in js:
            return self.artigos
        return {"url": self.url, "tem_main": True, "avisos": [], "desafios": [], "body": ""}


resp_rog = timeline(tweet("51", "lucia", "@ana concordo", in_reply_to_status_id_str="50"))
lt = X.Leitor(PaginaG({"https://x.com/lucia/with_replies": [RespG("UserRepliesTimeline", resp_rog),
                                                                RespG("ExploreSidebar", {"data": {}})]}),
              dormir=lambda s: None)
check([t["id"] for t in lt.respostas_da_conta("lucia")] == ["51"], "nome novo (UserRepliesTimeline): lê as respostas")
lt = X.Leitor(PaginaG({"https://x.com/lucia/with_replies": [RespG("UserPostsAndRepliesTimeline", resp_rog)]}),
              dormir=lambda s: None)
check([t["id"] for t in lt.respostas_da_conta("lucia")] == ["51"],
      "nome que ainda nem existe, mas de linha do tempo: lê do mesmo jeito")
lt = X.Leitor(PaginaG({"https://x.com/lucia/with_replies": [RespG("AlgoNovo", resp_rog)]}, artigos=18),
              dormir=lambda s: None)
try:
    lt.respostas_da_conta("lucia")
    check(False, "tela cheia e leitura vazia devia parar")
except X.ErroX as e:
    check(e.tipo == "LEITURA", "tela com posts e leitura vazia: para (sem a trava de 'já respondi' nada segue)")
lt = X.Leitor(PaginaG({}, artigos=0), dormir=lambda s: None)
check(lt.respostas_da_conta("lucia") == [], "conta que nunca respondeu (tela vazia): segue normal")

print(f"\nOK: {_ok} | FALHOU: {_fail}")
sys.exit(1 if _fail else 0)
