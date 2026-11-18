#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Replai · cópia de segurança dos dados (Documentos\Replai\). Só biblioteca padrão: o instalador usa
# antes de existir qualquer outra coisa.
"""Os dados de quem opera ficam fora da skill, em Documentos\\Replai\\: quem opera, e por conta a
configuração, a voz e o histórico dela, o material, a planilha e o registro do que já foi comentado
(é ele que garante "nunca o mesmo post duas vezes"). Atualizar o Replai não toca neles; esta cópia é
para o que acontece fora do instalador: a pasta trocada ou apagada numa atualização feita à mão, um PC
novo. Fica de fora o que é do PC ou se refaz sozinho: a sessão do navegador (cada PC loga de novo),
a rodada em curso, os caches e os prints de falha."""
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path


def pasta_documentos():
    """Documentos do Windows (respeita o redirecionamento para o OneDrive); no Mac, ~/Documents."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except Exception:  # noqa: BLE001
            pass
    for nome in ("Documents", "Documentos"):
        p = Path.home() / nome
        if p.is_dir():
            return p
    return Path.home()


def pasta_dados():
    """Documentos\\Replai\\ (REPLAI_DIR troca, para testes)."""
    return Path(os.environ["REPLAI_DIR"]) if os.environ.get("REPLAI_DIR") else pasta_documentos() / "Replai"

COPIAS = "_copias"                  # dentro de Documentos\Replai\
GUARDAR = 10
FORA = {"navegador", "linkedin-navegador", "rodada", "__pycache__"}
FORA_PREFIXO = ("cache-", ".")
FORA_SUFIXO = (".tmp", ".lock", ".log")


def _entra(rel):
    """Um arquivo de dentro da pasta de uma conta entra na cópia?"""
    nome = rel.parts[-1]
    return not (any(p in FORA for p in rel.parts) or nome.startswith(FORA_PREFIXO) or nome.endswith(FORA_SUFIXO))


def contas(base):
    base = Path(base)
    return sorted(p.name for p in base.iterdir() if (p / "conta.json").is_file()) if base.is_dir() else []


def fazer_copia(base, motivo="manual"):
    """Zip com o que importa em `base`; guarda as GUARDAR mais recentes. None se não há dado nenhum."""
    base = Path(base)
    nomes = contas(base)
    if not nomes and not (base / "operador.json").is_file():
        return None
    destino = base / COPIAS
    destino.mkdir(parents=True, exist_ok=True)
    zipado = destino / f"replai-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{motivo}.zip"
    arquivos = 0
    with zipfile.ZipFile(zipado, "w", zipfile.ZIP_DEFLATED) as z:
        if (base / "operador.json").is_file():
            z.write(base / "operador.json", "operador.json")
            arquivos += 1
        for conta in nomes:
            for f in sorted((base / conta).rglob("*")):
                rel = f.relative_to(base)
                if f.is_file() and _entra(rel):
                    z.write(f, rel.as_posix())
                    arquivos += 1
        z.writestr("_copia.json", json.dumps({"quando": datetime.now().isoformat(timespec="seconds"),
                                              "motivo": motivo, "contas": nomes}, ensure_ascii=False))
    for velha in sorted(destino.glob("replai-*.zip"))[:-GUARDAR]:
        velha.unlink()
    return {"arquivo": str(zipado), "contas": nomes, "arquivos": arquivos}


def copias(base):
    return [str(p) for p in sorted((Path(base) / COPIAS).glob("replai-*.zip"), reverse=True)]


def restaurar(base, zipado, substituir=False):
    """Põe de volta o que estiver no zip. Conta que já existe no PC fica como está, a não ser com
    `substituir` (e aí a atual vira uma cópia antes): o registro de uma conta em uso nunca é misturado
    com o de outra época."""
    base, zipado = Path(base), Path(zipado)
    with zipfile.ZipFile(zipado) as z:
        info = json.loads(z.read("_copia.json")) if "_copia.json" in z.namelist() else {}
        nomes = sorted({Path(n).parts[0] for n in z.namelist() if len(Path(n).parts) > 1})
        existentes = [c for c in nomes if (base / c / "conta.json").is_file()]
        if existentes and substituir:
            fazer_copia(base, "antes-de-restaurar")
        pular = set() if substituir else set(existentes)
        voltou = []
        for n in z.namelist():
            partes = Path(n).parts
            if n == "_copia.json" or (len(partes) > 1 and partes[0] in pular):
                continue
            if len(partes) == 1 and (base / n).exists() and not substituir:
                continue
            z.extract(n, base)
            if len(partes) > 1 and partes[0] not in voltou:
                voltou.append(partes[0])
    return {"de": info.get("quando"), "contas_restauradas": voltou, "ja_existiam": sorted(pular)}
