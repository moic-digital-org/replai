#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Replai · harness PURO (sem rede, sem navegador) da leitura Voyager do LinkedIn.
"""Trava os parsers do replai_voyager (porte do parse.ts da extensao Replai Comercial, com as MESMAS
fixtures sinteticas dela) e a tabela de erros que para a rodada.

Cobre:
  1. data do post a partir do id da activity;
  2. hidratacao do formato normalizado (refs *campo, inclusive em lista);
  3. posts de um perfil (normalizado e simples): texto, autor, contagens, curtido, imagem, repost;
  4. o comentario da conta: acha o dela e IGNORA a mencao a ela no comentario de outro;
  5. classificar_status: 0/3xx/429/999 = bloqueio, 401 = sessao, 403 so' bloqueia na 3a seguida;
  6. o cliente Voyager com pagina falsa: conta a leitura, respeita a pausa, levanta no bloqueio.
Rodar:  python replai_voyager_test.py
"""
import io
import json
import sys

import linkedin as RV

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ok = 0
_fail = 0


def check(cond, label):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  [OK ] {label}")
    else:
        _fail += 1
        print(f"  [FAIL] {label}")


def id_em(iso):
    """O id de activity que carrega este instante (o inverso de data_da_activity)."""
    from datetime import datetime
    ms = int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)
    return str(ms << 22)


ACT = id_em("2026-09-20T10:00:00Z")
ACT2 = id_em("2026-09-18T09:00:00Z")
ORIG = id_em("2026-09-17T09:00:00Z")


def upd(i):
    return f"urn:li:fs_updateV2:(urn:li:activity:{i},MEMBER_SHARES,EMPTY,DEFAULT,false)"


print("\n== 1. data do post sai do id da activity ==")
check(RV.data_da_activity(ACT) == "2026-09-20T10:00:00.000Z", "id -> 2026-09-20T10:00:00.000Z")
check(RV.data_da_activity("123") is None, "id curto demais -> None")
check(RV.data_da_activity("abc") is None, "id nao numerico -> None")

print("\n== 2. hidratar resolve *campo, inclusive em listas ==")
h = RV.hidratar({"data": {"*elements": ["a", "b"], "*x": "faltando"},
                 "included": [{"entityUrn": "a", "v": 1, "*filho": "c"},
                              {"entityUrn": "b", "v": 2}, {"entityUrn": "c", "v": 3}]})
check(h == {"elements": [{"entityUrn": "a", "v": 1, "filho": {"entityUrn": "c", "v": 3}},
                         {"entityUrn": "b", "v": 2}], "x": "faltando"},
      "refs resolvidas; ref sem alvo fica como veio")

print("\n== 3. posts de um perfil ==")
normalizado = {
    "data": {"*elements": [upd(ACT), upd(ACT2)], "metadata": {"paginationToken": "tok-1"}},
    "included": [
        {"entityUrn": upd(ACT), "updateMetadata": {"urn": f"urn:li:activity:{ACT}"},
         "actor": {"name": {"text": "Marina Couto"}, "description": {"text": "Head of Growth · Lumen"},
                   "navigationContext": {"actionTarget": "https://www.linkedin.com/in/marina-couto?miniProfileUrn=x"}},
         "commentary": {"text": {"text": "Como vocês medem retenção?"}},
         "*socialDetail": f"urn:li:fs_socialDetail:urn:li:activity:{ACT}",
         "content": {"com.linkedin.voyager.feed.render.ImageComponent": {"images": [{"attributes": [{"vectorImage": {
             "rootUrl": "https://media.licdn.com/dms/image/",
             "artifacts": [{"width": 1280, "fileIdentifyingUrlPathSegment": "big.jpg"},
                           {"width": 800, "fileIdentifyingUrlPathSegment": "mid.jpg"},
                           {"width": 160, "fileIdentifyingUrlPathSegment": "small.jpg"}]}}]}]}}},
        {"entityUrn": f"urn:li:fs_socialDetail:urn:li:activity:{ACT}",
         "*totalSocialActivityCounts": f"urn:li:fs_socialActivityCounts:urn:li:activity:{ACT}"},
        {"entityUrn": f"urn:li:fs_socialActivityCounts:urn:li:activity:{ACT}",
         "numLikes": 42, "numComments": 7, "numShares": 1, "liked": True},
        {"entityUrn": upd(ACT2), "updateMetadata": {"urn": f"urn:li:activity:{ACT2}"},
         "actor": {"name": {"text": "Marina Couto"}}, "*resharedUpdate": upd(ORIG)},
        {"entityUrn": upd(ORIG), "updateMetadata": {"urn": f"urn:li:activity:{ORIG}"},
         "commentary": {"text": {"text": "post original de outra pessoa"}}},
    ],
}
posts, tok, total = RV.ler_posts(normalizado)
check(total == 2 and tok == "tok-1", "2 elementos e o token de paginacao")
p, r = posts
check(p["activity_urn"] == f"urn:li:activity:{ACT}", "activity_urn do post")
check(p["url"] == f"https://www.linkedin.com/feed/update/urn:li:activity:{ACT}/", "url do post")
check(p["data"] == "2026-09-20T10:00:00.000Z", "data do post")
check(p["texto"] == "Como vocês medem retenção?", "texto do post")
check(p["autor_vanity"] == "marina-couto", "vanity do autor")
check(p["autor_headline"] == "Head of Growth · Lumen", "headline do autor")
check(p["n_curtidas"] == 42 and p["n_comentarios"] == 7, "contagens")
check(p["curtido_pela_conta"] is True, "a conta ja' curtiu (liked: true)")
check(p["imagem"] == "https://media.licdn.com/dms/image/mid.jpg", "imagem: a maior com ate' 800px")
check(p["repost_puro"] is False, "post proprio nao e' repost puro")
check(r["repost"] is True and r["repost_puro"] is True, "repost sem texto proprio = repost puro")
check(r["original_id"] == ORIG and p["original_id"] is None, "repost guarda o id do post original (dedupe)")
simples, _t, _n = RV.ler_posts({"elements": [
    {"updateMetadata": {"urn": f"urn:li:activity:{ACT}"}, "commentary": {"text": {"text": "oi"}},
     "socialDetail": {"totalSocialActivityCounts": {"numLikes": 3, "numComments": 0, "liked": False}}},
    {"semUrn": True}]})
check(len(simples) == 1 and simples[0]["curtido_pela_conta"] is False and simples[0]["n_curtidas"] == 3,
      "formato simples: elemento sem urn e' ignorado, contagens e curtida lidas")
reacao, _t, _n = RV.ler_posts({"elements": [
    {"updateMetadata": {"urn": f"urn:li:activity:{ACT}"},
     "socialDetail": {"totalSocialActivityCounts": {"reactionByViewer": "LIKE"}}}]})
check(reacao[0]["curtido_pela_conta"] is True, "reactionByViewer preenchido tambem conta como curtido")

print("\n== 4. o comentario da conta ==")
CONTA = {"urn": "ACoAABDxyz", "vanity": "bd-person"}
raw = {
    "data": {"*elements": [f"urn:li:fs_objectComment:(111,activity:{ACT})",
                           f"urn:li:fs_objectComment:(222,activity:{ACT})"]},
    "included": [
        {"entityUrn": f"urn:li:fs_objectComment:(111,activity:{ACT})",
         "commenter": {"com.linkedin.voyager.feed.MemberActor": {"*miniProfile": "urn:li:fs_miniProfile:ACoAAOTHER"}},
         "commentV2": {"text": "concordo com @BD", "attributes": [{"*miniProfile": "urn:li:fs_miniProfile:ACoAABDxyz"}]}},
        {"entityUrn": f"urn:li:fs_objectComment:(222,activity:{ACT})",
         "commenter": {"com.linkedin.voyager.feed.MemberActor": {"*miniProfile": "urn:li:fs_miniProfile:ACoAABDxyz"}},
         "commentV2": {"text": "Boa pergunta, Marina."}},
        {"entityUrn": "urn:li:fs_miniProfile:ACoAAOTHER", "publicIdentifier": "other"},
        {"entityUrn": "urn:li:fs_miniProfile:ACoAABDxyz", "publicIdentifier": "bd-person"},
    ],
}
achado = RV.comentario_da_pessoa(raw, CONTA)
check(achado == {"comment_urn": f"urn:li:comment:(activity:{ACT},222)", "texto": "Boa pergunta, Marina."},
      "acha o comentario da conta (e nao o de outro que a menciona)")
check(RV.comentario_da_pessoa(raw, {"urn": "ACoAAnobody", "vanity": "nobody"}) is None,
      "conta sem comentario no post -> None")
simples = {"elements": [{"urn": f"urn:li:comment:(activity:{ACT},333)",
                         "commenter": {"com.linkedin.voyager.feed.MemberActor": {"miniProfile": {"publicIdentifier": "bd-person"}}}}]}
check((RV.comentario_da_pessoa(simples, {"urn": "ACoAAdiferente", "vanity": "bd-person"}) or {}).get("comment_urn")
      == f"urn:li:comment:(activity:{ACT},333)", "formato simples, casando pela vanity")
check(RV.urn_do_comentario({"entityUrn": "urn:li:fs_objectComment:(9,ugcPost:8)"}) == "urn:li:comment:(ugcPost:8,9)",
      "fs_objectComment de ugcPost vira urn:li:comment")
check(RV.url_do_comentario(f"urn:li:activity:{ACT}", "urn:li:comment:(activity:1,2)").endswith(
      "commentUrn=urn%3Ali%3Acomment%3A%28activity%3A1%2C2%29"), "link do comentario com o urn codificado")
me = RV.ler_me({"data": {}, "included": [{"entityUrn": "urn:li:fs_miniProfile:ACoAAme",
                                          "publicIdentifier": "eu-mesmo", "firstName": "Ju", "lastName": "P"}]})
check(me == {"urn": "ACoAAme", "vanity": "eu-mesmo", "nome": "Ju P"}, "/me: urn, vanity e nome")
check(RV.urn_do_perfil({"included": [{"entityUrn": "urn:li:fsd_profile:ACoAAx", "publicIdentifier": "Fulano"}]},
                       "fulano") == "ACoAAx", "vanity -> URN, sem diferenciar maiusculas")

print("\n== 5. classificar_status ==")
check(RV.classificar_status(200, 2)[0] is None and RV.classificar_status(200, 2)[1] == 0,
      "200 ok zera a sequencia de 403")
check(RV.classificar_status(0, 0)[0] == RV.ERRO_BLOQUEIO, "status 0 (redirect para login) = bloqueio")
check(RV.classificar_status(302, 0)[0] == RV.ERRO_BLOQUEIO, "3xx = bloqueio")
check(RV.classificar_status(429, 0)[0] == RV.ERRO_BLOQUEIO, "429 = bloqueio")
check(RV.classificar_status(999, 0)[0] == RV.ERRO_BLOQUEIO, "999 = bloqueio")
check(RV.classificar_status(401, 0)[0] == RV.ERRO_SESSAO, "401 = sessao expirada")
check(RV.classificar_status(403, 0) == (RV.ERRO_HTTP, 1), "1a recusa 403 = so' http")
check(RV.classificar_status(403, 2)[0] == RV.ERRO_BLOQUEIO, "3a recusa 403 seguida = bloqueio")
check(RV.classificar_status(404, 1) == (RV.ERRO_NAO_ENCONTRADO, 0), "404 = nao encontrado (zera 403)")
check(RV.classificar_status(-1, 0)[0] == RV.ERRO_REDE, "-1 (fetch falhou) = rede")
check(RV.classificar_status(500, 0)[0] == RV.ERRO_HTTP, "500 = http")

print("\n== 6. o cliente Voyager com pagina falsa ==")


class Pagina:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.caminhos = []

    def evaluate(self, js, args):
        assert js is RV.JS_VOYAGER_GET
        self.caminhos.append(args[0])
        return json.dumps(self.respostas.pop(0))


class Relogio:
    def __init__(self):
        self.t = 100.0
        self.dormiu = []

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.dormiu.append(s)
        self.t += s


rel = Relogio()
lidas = []
pag = Pagina([{"status": 200, "j": {"included": [{"entityUrn": "urn:li:fsd_profile:ACoAAme",
                                                  "publicIdentifier": "eu"}]}},
              {"status": 200, "j": normalizado},
              {"status": 429}])
voy = RV.Voyager(pag, pausa_seg=(3, 3), ao_ler=lidas.append, relogio=rel, dormir=rel.dormir)
check(voy.pronta(), "pronta antes da primeira leitura")
check(voy.me()["vanity"] == "eu", "me() devolve a conta logada")
check(not voy.pronta() and voy.segundos_ate_pronta() == 3, "depois de ler, espera a pausa (3s)")
ps = voy.posts("ACoAAlead")
check(len(ps) == 2 and rel.dormiu == [3], "ler cedo dorme so' o que falta da pausa")
check("profileUrn=urn%3Ali%3Afsd_profile%3AACoAAlead" in pag.caminhos[1], "caminho dos posts leva o URN")
try:
    voy.posts("ACoAAlead")
    check(False, "429 devia levantar VoyagerErro de bloqueio")
except RV.VoyagerErro as e:
    check(e.tipo == RV.ERRO_BLOQUEIO and e.status == 429, "429 levanta VoyagerErro(bloqueio)")
check(lidas == ["me", "posts", "posts"] and voy.feitas == 3, "toda request e' contada (inclusive a que falhou)")


class PaginaQuebrada:
    def evaluate(self, js, args):
        raise RuntimeError("Execution context was destroyed")


try:
    RV.Voyager(PaginaQuebrada(), relogio=rel, dormir=rel.dormir).posts("x")
    check(False, "pagina quebrada devia levantar")
except RV.VoyagerErro as e:
    check(e.tipo == RV.ERRO_REDE, "pagina navegando/fechada vira erro de REDE, nao bloqueio")

class PaginaNavegando(Pagina):
    """A primeira leitura cai porque a página ainda navegava (visto na tela real em 27/10/2026)."""
    def __init__(self, respostas, quedas=1):
        super().__init__(respostas)
        self.quedas = quedas

    def evaluate(self, js, args):
        if self.quedas:
            self.quedas -= 1
            raise RuntimeError("Page.evaluate: Execution context was destroyed, most likely because of a navigation")
        return super().evaluate(js, args)

    def wait_for_load_state(self, *a, **kw):
        pass


ME_OK = {"status": 200, "j": {"included": [{"entityUrn": "urn:li:fsd_profile:ACoAAme", "publicIdentifier": "eu"}]}}
v = RV.Voyager(PaginaNavegando([ME_OK]), dormir=lambda s: None)
check(v.me()["vanity"] == "eu" and v.feitas == 1, "página ainda navegando: espera, lê de novo e conta uma leitura só")
v = RV.Voyager(PaginaNavegando([ME_OK], quedas=3), dormir=lambda s: None)
try:
    v.me()
    check(False, "três quedas seguidas deviam virar erro")
except RV.VoyagerErro as e:
    check(e.tipo == RV.ERRO_REDE, "três quedas seguidas: erro de rede (não bloqueio, não fica tentando para sempre)")

class PaginaNoX(Pagina):
    """A aba é das duas redes: pode estar no X quando a leitura do LinkedIn chega."""
    url = "https://x.com/i/lists/1"

    def goto(self, url, **kw):
        self.url = url


p_x = PaginaNoX([ME_OK])
check(RV.Voyager(p_x, dormir=lambda s: None).me()["vanity"] == "eu" and "linkedin.com" in p_x.url,
      "aba no X: volta ao LinkedIn antes de ler (o cookie é dele)")

print("\n== 7. bloqueio na tela (classificar_bloqueio) ==")
check(RV.classificar_bloqueio({"url": "https://www.linkedin.com/checkpoint/challenge/x", "tem_main": True}) == "CAPTCHA",
      "url de checkpoint = CAPTCHA")
check(RV.classificar_bloqueio({"url": "https://www.linkedin.com/login/?session_redirect=x", "tem_main": True}) == "SESSAO"
      and RV.classificar_bloqueio({"url": "https://www.linkedin.com/authwall?x", "tem_main": True}) == "SESSAO",
      "tela de login = sessão caída (pede login), não captcha")
check(RV.classificar_bloqueio({"url": "https://www.linkedin.com/feed/", "tem_main": True,
                               "desafios": ["https://client-api.arkoselabs.com/fc/x"]}) == "CAPTCHA",
      "iframe de desafio = CAPTCHA")
check(RV.classificar_bloqueio({"url": "https://www.linkedin.com/feed/", "tem_main": True,
                               "avisos": ["You've reached the weekly limit"]}) == "LIMIT", "aviso de limite = LIMIT")
check(RV.classificar_bloqueio({"url": "https://www.linkedin.com/feed/", "tem_main": False, "avisos": [],
                               "body": "We noticed unusual activity on your account"}) == "CAPTCHA",
      "sem main e texto de atividade incomum = CAPTCHA")
check(RV.classificar_bloqueio({"url": "https://www.linkedin.com/feed/", "tem_main": True, "avisos": []}) is None,
      "página normal = nada")
check(RV.classificar_bloqueio(None) is None, "leitura falhou = nada (não inventa bloqueio)")

print("\n== 8. os scripts da página num navegador de verdade (layout novo e antigo) ==")
# Cópia mínima do que o LinkedIn mostrou num post em 27/10/2026 (layout novo) e do layout antigo.
POST_NOVO = """<main><div class="card">
  <div data-testid="ReactionFacepileCollection-urn:li:activity:111"><a href="https://www.linkedin.com/feed/update/urn:li:activity:111/">205</a></div>
  <button aria-label="Situação do botão de reação: nenhuma reação">205</button>
  <button aria-label="Abrir menu de reações">v</button>
  <button aria-label="Comentar">21</button>
  <div componentkey="commentBox-x"><div><div role="textbox" contenteditable="true" aria-label="Editor de texto para criar comentário"></div></div>
    <button>Comentar</button></div>
  <div componentkey="replaceableComment_urn:li:comment:(activity:111,9)"><a href="/in/fulano/">Fulano</a>
    <p>Liquidação no mesmo dia muda o caixa.</p><button aria-label="Abrir menu de reações">v</button><button aria-label="Responder">r</button></div>
</div></main>"""
POST_ANTIGO = """<main><div data-urn="urn:li:activity:222">
  <button class="react-button__trigger" aria-pressed="false" aria-label="Gostei">Gostei</button>
  <button class="comment-button" aria-label="Comentar">Comentar</button>
  <div class="comments-comment-box"><form><div contenteditable="true"></div>
    <button class="comments-comment-box__submit-button">Publicar</button></form></div>
</div></main>"""
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        pg = nav.new_page()
        pg.set_content(POST_NOVO)
        k = RV.controles(pg, "111")
        check(k.get("achou_post") and k.get("layout") == "novo" and k["like"]["pressionado"] == "false"
              and k["comentar"]["achou"] and k["editor"] and k["enviar"]["achou"],
              "layout novo: acha o post, o curtir (não curtido), comentar, a caixa e o enviar")
        check(RV.controles(pg, "999").get("achou_post") is False, "id de outro post: não acha nada (não clica no post errado)")
        c_ = RV.comentarios_na_pagina(pg, "fulano", "Liquidação no mesmo dia")
        check(c_.get("da_conta") and c_.get("com_trecho"), "layout novo: vê o comentário da conta e o trecho publicado")
        pg.set_content(POST_NOVO.replace("nenhuma reação", "Gostei"))
        check(RV.controles(pg, "111")["like"]["pressionado"] == "true", "layout novo: já curtido não autoriza clicar de novo")
        pg.set_content(POST_NOVO.replace('<button aria-label="Comentar">21</button>',
                                         '<button aria-label="Situação do botão de reação: nenhuma reação">1</button>'))
        check(RV.controles(pg, "111").get("achou_post") is False, "dois curtir no mesmo bloco: ambíguo, não acha (fail-closed)")
        pg.set_content('<main><div componentkey="replaceableComment_urn:li:comment:(activity:1,2)">'
                       '<a href="/in/lucia-prado/">Lúcia</a><div data-testid="expandable-text-box">Parabéns pelo lançamento!</div>'
                       '</div><div componentkey="replaceableComment_urn:li:comment:(activity:1,3)"><a href="/in/outra/">Outra</a>'
                       '<div data-testid="expandable-text-box">Não é da conta</div></div></main>')
        check(RV._json(pg, RV.JS_COMENTARIOS_PROPRIOS, ["lucia-prado"]) == ["Parabéns pelo lançamento!"],
              "layout novo: lê os comentários da própria conta (a voz) e só os dela")
        pg.set_content(POST_ANTIGO)
        k = RV.controles(pg, "222")
        check(k.get("achou_post") and k.get("layout") == "antigo" and k["like"]["pressionado"] == "false"
              and k["editor"] and k["enviar"]["achou"], "layout antigo continua funcionando")
        nav.close()
except Exception as e:  # noqa: BLE001 - sem navegador do Playwright no PC: avisa, não finge que passou
    check(False, f"navegador para o teste da página: {type(e).__name__}: {e}")

print("\n== publicar com outro elemento por cima do botão (16/11, conta real) ==")


class PaginaCoberta:
    """O clique do Playwright esbarra em algo por cima (ele não clica); o clique pelo botão funciona."""
    def __init__(self, ja_na_pagina=False, erro="Locator.click: Timeout 8000ms exceeded. <div> intercepts pointer events"):
        self.ja, self.erro, self.cliques_js = ja_na_pagina, erro, 0

    def locator(self, _sel):
        pg = self
        class L:
            first = property(lambda s: s)
            def click(s, timeout=0):
                raise TimeoutError(pg.erro)
        return L()

    def evaluate(self, js, args=None):
        if js is RV.JS_COMENTARIOS:
            return json.dumps({"com_trecho": self.ja})
        self.cliques_js += 1
        return True


pg = PaginaCoberta()
check(RV._clicar_publicar(pg, "fulano", "texto do comentario") is None and pg.cliques_js == 1,
      "coberto e ainda não na página: clica pelo próprio botão (uma vez)")
pg = PaginaCoberta(ja_na_pagina=True)
check(RV._clicar_publicar(pg, "fulano", "texto do comentario") is None and pg.cliques_js == 0,
      "coberto mas o comentário já está na página: não clica de novo")
pg = PaginaCoberta(erro="Locator.click: Target page, context or browser has been closed")
m = RV._clicar_publicar(pg, "fulano", "texto do comentario")
check(m and "pode ter saido" in m and pg.cliques_js == 0, "outro erro no clique: continua incerto, sem segundo clique")

print(f"\nOK: {_ok} | FALHOU: {_fail}")
sys.exit(1 if _fail else 0)
