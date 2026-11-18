#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Replai · instalador. O Claude roda quando pedem "instala o Replai"; o instalar.bat também chama este.
"""Instala a skill /replai: copia a skill e os ajudantes para ~/.claude, instala só o que faltar
(openpyxl, playwright, pypdf, o navegador e o Claude Code de linha de comando, que o vigia usa) e imprime
em JSON o que ficou. Não atualiza biblioteca que já existe: outros robôs do PC podem depender dela.
Os dados (Documentos\\Replai\\) não são tocados; antes de copiar, guarda uma cópia deles (dados.py).

    python scripts/instalar.py [--sem-claude-code]
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ORIGEM = Path(__file__).resolve().parent.parent
CLAUDE = Path.home() / ".claude"
DESTINO = CLAUDE / "skills" / "replai"
CHROME = (r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
          r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
          r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
          r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
          r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe",
          "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
# O Claude Code no Mac: o instalador oficial (põe o `claude` em ~/.local/bin).
CLAUDE_CODE_MAC = "curl -fsSL https://claude.ai/install.sh | bash"


def rodar(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode == 0, (p.stderr or p.stdout or "").strip()[-300:]


def achar_claude():
    """O `claude` do PATH ou onde os instaladores põem (a mesma busca do replai.caminho_claude)."""
    achado = shutil.which("claude")
    if achado:
        return achado
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
    candidatos = [Path.home() / ".local" / "bin" / "claude", Path.home() / ".local" / "bin" / "claude.exe",
                  winget / "Links" / "claude.exe", *sorted(winget.glob("Packages/Anthropic.ClaudeCode_*/claude.exe"))]
    return next((str(p) for p in candidatos if p.is_file()), None)


def instalar_bibliotecas(requisitos):
    pip = [sys.executable, "-m", "pip", "install", "--quiet", "-r", str(requisitos)]
    ok, msg = rodar(pip)
    if not ok and "externally-managed" in msg:     # Python do Homebrew (Mac): só aceita na pasta do usuário
        ok, msg = rodar(pip + ["--user", "--break-system-packages"])
    return ok, msg


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # a saída (JSON com acentos) é para o Claude ler
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(prog="instalar.py")
    ap.add_argument("--sem-claude-code", action="store_true")
    ap.add_argument("--so-a-skill", action="store_true",
                    help="copia a skill e os ajudantes e não instala nada (os testes usam)")
    args = ap.parse_args()
    r = {"python": sys.version.split()[0], "skill": str(DESTINO)}
    if sys.version_info < (3, 9):
        r["erro"] = "precisa do Python 3.9 ou mais novo"
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1

    import dados                         # ao lado deste arquivo; só biblioteca padrão
    base = dados.pasta_dados()
    copia = dados.fazer_copia(base, "antes-de-atualizar")
    if copia:
        r["dados"] = f"guardados: {', '.join(copia['contas']) or 'quem opera'} (cópia em {base / dados.COPIAS})"
    if base.resolve() in ORIGEM.resolve().parents or base.resolve() == ORIGEM.resolve():
        r["aviso"] = (f"o Replai está sendo instalado de dentro da pasta de dados ({base}). Essa pasta é só "
                      "dos dados: para atualizar, use o link do repositório ou um zip descompactado em outro "
                      "lugar, e nunca apague nem troque a pasta de dados")
    if ORIGEM != DESTINO:
        shutil.copytree(ORIGEM, DESTINO, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "docs", "*.zip", "CLAUDE.md"))
        commit = ""
        if (ORIGEM / ".git").exists():
            try:
                commit = subprocess.run(["git", "-C", str(ORIGEM), "rev-parse", "HEAD"], capture_output=True,
                                        text=True).stdout.strip()
            except OSError:
                pass
        if len(commit) == 40:   # o `replai.py atualizacao` compara com a main do GitHub, pelo clone de onde veio
            (DESTINO / "versao.json").write_text(json.dumps({"commit": commit, "origem": str(ORIGEM)}),
                                                 encoding="utf-8")
            r["versao"] = commit[:7]
    (CLAUDE / "agents").mkdir(parents=True, exist_ok=True)
    for a in (DESTINO / "agentes").glob("*.md"):
        shutil.copy2(a, CLAUDE / "agents" / a.name)
    r["ajudantes"] = "replai-escritor, replai-voz"
    if args.so_a_skill:
        r["pronto"] = True
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0

    faltam = [m for m in ("openpyxl", "playwright", "pypdf") if importlib.util.find_spec(m) is None]
    if faltam:
        ok, msg = instalar_bibliotecas(DESTINO / "requirements.txt")
        r["bibliotecas"] = "instaladas: " + ", ".join(faltam) if ok else f"falhou: {msg}"
    else:
        r["bibliotecas"] = "ok"

    if any(os.path.exists(os.path.expandvars(c)) for c in CHROME):
        r["navegador"] = "do PC (Chrome ou Brave)"
    else:
        ok, msg = rodar([sys.executable, "-m", "playwright", "install", "chromium"])
        r["navegador"] = "Chromium do Playwright" if ok else f"falhou: {msg}"

    if achar_claude():
        r["claude_code"] = "ok"
    elif args.sem_claude_code:
        r["claude_code"] = "pulado (o vigia precisa dele)"
    elif os.name == "nt" and shutil.which("winget"):
        ok, msg = rodar(["winget", "install", "-e", "--id", "Anthropic.ClaudeCode",
                         "--accept-package-agreements", "--accept-source-agreements"])
        ok = ok or bool(achar_claude())        # "já instalado" o winget responde com erro
        r["claude_code"] = "instalado (aparece numa conversa nova)" if ok else f"falhou: {msg}"
    elif sys.platform == "darwin":
        ok, msg = rodar(["bash", "-c", CLAUDE_CODE_MAC])
        r["claude_code"] = "instalado (aparece numa conversa nova)" if ok else f"falhou: {msg}"
    else:
        r["claude_code"] = "faltando: instale o Claude Code de linha de comando (o vigia precisa)"

    r["pronto"] = not any("falhou" in str(v) for v in r.values())
    r["proximo"] = "abra uma conversa nova no Claude e digite /replai"
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r["pronto"] else 1


if __name__ == "__main__":
    sys.exit(main())
