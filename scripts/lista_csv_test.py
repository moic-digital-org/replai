#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rodar:  python lista_csv_test.py   (sem rede, sem navegador)"""
import sys
import tempfile
from pathlib import Path

import lista_csv as LC

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass
_ok = _fail = 0


def check(cond, label):
    global _ok, _fail
    _ok, _fail = (_ok + 1, _fail) if cond else (_ok, _fail + 1)
    print(f"  [{'OK ' if cond else 'FAIL'}] {label}")


print("\n== reconhecer perfis ==")
check(LC.classificar("https://www.linkedin.com/in/Lia-Melo/?utm=1") == ("linkedin", "https://www.linkedin.com/in/lia-melo/"),
      "link do LinkedIn vira o link limpo")
check(LC.classificar("@LiaMelo") == ("x", "@liamelo") and LC.classificar("https://x.com/liamelo/status/1") == ("x", "@liamelo")
      and LC.classificar("twitter.com/liamelo") == ("x", "@liamelo"), "@, link do X e do Twitter viram @")
check(LC.classificar("Lia Melo") is None and LC.classificar("") is None, "nome solto não é perfil")

print("\n== ler o que vem do Excel ==")
t = "﻿Nome;LinkedIn;X;Prioridade;Incluir;Observação\r\nLia Melo;https://www.linkedin.com/in/lia-melo/;@liamelo;alta;Sim;CEO\r\n"
ls = LC.ler_texto(t)
check(len(ls) == 1 and ls[0]["X"] == "@liamelo" and ls[0]["Prioridade"] == "alta", "separador ';' (Excel em português)")
ls = LC.ler_texto("name,linkedin,twitter\nRui,https://www.linkedin.com/in/rui/,@rui\n")
check(ls[0]["Nome"] == "Rui" and ls[0]["X"] == "@rui", "vírgula e cabeçalho em inglês")
check(LC.ler_texto("") == [] and LC.ler_texto("Nome;LinkedIn;X\n") == [], "vazio e só cabeçalho")

print("\n== adicionar, tirar, pausar ==")
ls, como = LC.adicionar([], ["https://www.linkedin.com/in/lia-melo/"], nome="Lia Melo")
check(como == "nova" and ls[0]["Incluir"] == "Sim" and ls[0]["Prioridade"] == "normal", "pessoa nova entra ativa")
ls, como = LC.adicionar(ls, ["@liamelo"], nome="Lia Melo")
check(como == "atualizada" and len(ls) == 1 and ls[0]["X"] == "@liamelo", "o @ da mesma pessoa completa a linha (pelo nome)")
ls, como = LC.adicionar(ls, ["https://www.linkedin.com/in/lia-melo/"], prioridade="alta")
check(como == "atualizada" and len(ls) == 1 and ls[0]["Prioridade"] == "alta", "mesmo perfil não duplica")
ls, como = LC.adicionar(ls, ["https://www.linkedin.com/in/outra-lia/"], nome="Lia Melo")
check(como == "nova" and len(ls) == 2, "mesmo nome com outro perfil é outra pessoa")
check(LC.achar(ls, "Lia Melo") is None, "nome repetido não escolhe ninguém")
try:
    LC.adicionar(ls, ["Lia"])
    check(False, "texto que não é perfil é recusado")
except ValueError:
    check(True, "texto que não é perfil é recusado")
ls, p = LC.incluir(ls, "@liamelo", False)
check(p["Incluir"] == "Não" and not LC.ativa(p), "pausar não apaga")
ls, p = LC.incluir(ls, "https://x.com/liamelo", True)
check(LC.ativa(p), "retomar pelo link do X")
ls, tirada = LC.tirar(ls, "https://www.linkedin.com/in/outra-lia/")
check(len(ls) == 1 and tirada["LinkedIn"].endswith("/outra-lia/"), "tirar pelo link")
try:
    LC.tirar(ls, "@ninguem")
    check(False, "tirar quem não está avisa")
except LookupError:
    check(True, "tirar quem não está avisa")

print("\n== gravar e ler de volta ==")
d = Path(tempfile.mkdtemp())
LC.gravar(d / "lista.csv", ls)
bruto = (d / "lista.csv").read_bytes()
check(bruto.startswith(b"\xef\xbb\xbf") and b";" in bruto.split(b"\r\n")[0], "UTF-8 com BOM e ';' (abre certo no Excel)")
check(LC.ler(d / "lista.csv") == ls, "ida e volta sem perder nada")
check(not (d / "lista.csv.tmp").exists(), "sem arquivo temporário sobrando")

print("\n== juntar listas antigas ==")
ls = LC.juntar({"linkedin": [{"Nome": "Lia Melo", "Perfil": "https://www.linkedin.com/in/lia-melo/", "Prioridade": "alta"},
                             {"Nome": "Rui", "Perfil": "https://www.linkedin.com/in/rui/", "Incluir": "Não"}],
                "x": [{"Nome": "Lia Melo", "Perfil": "@liamelo"}, {"Nome": "Ana", "Perfil": "@ana"},
                      {"Nome": "Ana", "Perfil": "@ana"}]})
check(len(ls) == 3, "uma linha por pessoa (Lia nas duas redes, Ana repetida)")
lia = ls[0]
check(lia["LinkedIn"].endswith("/lia-melo/") and lia["X"] == "@liamelo" and lia["Prioridade"] == "alta", "Lia junta as duas redes")
check(ls[1]["Incluir"] == "Não", "quem estava pausado continua pausado")

print(f"\nOK: {_ok} | FALHOU: {_fail}")
sys.exit(1 if _fail else 0)
