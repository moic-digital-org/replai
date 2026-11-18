# Replai

Skill do Claude Code (`/replai`) que comenta nos posts dos perfis de uma lista, no LinkedIn e no X, na
voz da conta, e posta sozinha (curte e comenta/responde). As duas redes andam juntas: um navegador,
uma aba só que as redes revezam, escondida, um escritor só e a postagem das duas ao mesmo tempo. Nas primeiras rodadas quem
opera revisa no chat, e cada correção vira aprendizado; depois de 3 rodadas seguidas sem correção numa
rede, ela pode passar para o **modo sozinho** (posta sem esperar aprovação). O **modo vigia** responde entre 5 e 25
minutos depois de alguém da lista postar (no X pela Lista, no LinkedIn pelo sininho). Nunca comenta
duas vezes no mesmo post. Conversa em português ou inglês.


> **Aviso / Disclaimer.** O Replai automatiza ações numa conta pessoal do LinkedIn e do X (ler posts, curtir e
> comentar). Os termos de uso das duas redes restringem automação e podem levar a limite, verificação,
> suspensão ou banimento da conta. Use por sua conta e risco, só em contas que você opera com autorização,
> e respeite os termos de cada rede e as leis aplicáveis, inclusive de proteção de dados. O Replai não é
> afiliado ao LinkedIn, ao X nem à Anthropic, e é distribuído "no estado em que se encontra", sem garantia
> (licença MIT, em `LICENSE`). Os tetos e pausas do script reduzem o risco, mas não o eliminam.
>
> *Replai automates actions on personal LinkedIn and X accounts. Both platforms' terms restrict
> automation and may lead to rate limits, verification, suspension or a ban. Use at your own risk, only on
> accounts you are authorized to operate, and comply with each platform's terms and applicable law. Not
> affiliated with LinkedIn, X or Anthropic. Provided "as is", without warranty (MIT License).*

## Instalar pelo Claude, com o link do GitHub

No app do Claude (aba Code), peça: **"instala o Replai: clone https://github.com/moic-digital-org/replai
e siga o README"**. Depois é conversa: `/replai`. O repositório é público: não precisa de conta no GitHub.

Para atualizar: o `/replai` avisa quando a `main` tem versão nova e atualiza com o ok de quem opera
(`replai.py atualizacao`, que usa o clone e o login do GitHub guardados na instalação).

**Para o Claude que está instalando** (comece avisando numa linha: "Vou pedir permissão algumas
vezes: clique em Permitir."). `<pasta>` é `~/Downloads/replai`, só do código; nunca a pasta de dados
`Documentos\Replai`.

1. **Python.** `python`, ou `py -3` (se abrir a Microsoft Store, não serve; no Mac, `python3`). Sem
   Python, no Windows: `winget install -e --id Python.Python.3.12 --scope user`, e use
   `%LocalAppData%\Programs\Python\Python312\python.exe`; no Mac: `xcode-select --install`.
2. **Baixar.** Sem `git`: no Windows `winget install -e --id Git.Git`; no Mac `xcode-select --install`.
   - `<pasta>` não existe: `git clone --depth 1 https://github.com/moic-digital-org/replai.git <pasta>`.
   - `<pasta>` já existe (atualização): `git -C <pasta> pull --ff-only`. Se recusar, apague só
     `<pasta>` e clone de novo.
   - "Repository not found": confira o link (`https://github.com/moic-digital-org/replai`).
3. **Instalar.** `<python> <pasta>/scripts/instalar.py`. Ele copia a skill para
   `~/.claude/skills/replai/` e os ajudantes `replai-escritor` e `replai-voz` para `~/.claude/agents/`,
   guarda uma cópia dos dados antes (em `Documentos\Replai\_copias\`) e instala só o que faltar
   (`openpyxl`, `playwright`, `pypdf`, o navegador e o Claude Code de linha de comando, que o vigia
   usa). Os dados não são tocados.
4. **Fim.** Mostre o resultado em até 3 linhas e termine com: "Pronto. Agora: 1. Abra uma conversa
   nova (na mesma pasta). 2. Digite /replai." Não siga a configuração nesta conversa: os ajudantes só
   carregam numa conversa nova.

Sem o Claude (Windows): no GitHub, **Code > Download ZIP**, descompacte em `Downloads` e dois cliques
em `instalar.bat` (garante o Python e roda o mesmo `instalar.py`). Quem já usa a campanha de DM no mesmo PC: o
navegador é o da campanha, e o LinkedIn já vem logado.

## Combinados

- **Várias contas num PC, cada conta num PC só.** Um PC opera quantas contas quiser (cada uma com o
  login, a voz e a lista dela, e um navegador por vez). O registro do que já foi comentado fica no PC:
  a mesma conta em dois PCs dobra o volume do dia.
- Os limites (teto por dia, aquecimento da conta, horário, pausas, parada no captcha) são do script e
  não se furam.
- O vigia precisa do computador ligado e da sessão aberta (Windows ou Mac).

## Por dentro

| Arquivo | O que é |
|---|---|
| `SKILL.md` | o roteiro da conversa (roda em Sonnet) |
| `scripts/replai.py` | a CLI: configurar, conta, listas, registro, planilha, coleta, escrita, revisão, postagem, vigia |
| `scripts/regra.py` | regras puras: validador anti-IA, seleção, regra nº 1, tetos, aprendizado, vigia |
| `scripts/linkedin.py` · `scripts/x.py` | leitura e cliques de cada rede |
| `scripts/instalar.py` | o instalador (o Claude roda; o `instalar.bat` também chama) |
| `scripts/dados.py` | a pasta de dados e a cópia de segurança (o instalador usa antes de atualizar) |
| `referencias/` | doutrina do comentário, molde e roteiro da voz, configuração, comandos, problemas |
| `agentes/` | os subagentes escritor (Sonnet) e voz (Opus) |

Testes, sem framework: `cd scripts && python regra_test.py && python linkedin_test.py && python
x_test.py && python lista_csv_test.py && python replai_test.py`.

Spec e planos em `docs/superpowers/`. Guia para quem opera: `LEIA-ME.md`.

---

## English

`/replai` is a Claude Code skill that comments on posts from a list of profiles on LinkedIn and X, in
the account's voice, and posts by itself: both networks together, in one browser, with operator review
in the first rounds and learning from every correction. After 3 reviewed rounds in a row with no correction on a network, it can switch to **autopilot** (posts without approval). **Watch mode** replies 5 to 25 minutes after
someone on the list posts. It never comments twice on the same post. To install, ask Claude (Code
tab) to "install Replai: https://github.com/moic-digital-org/replai" (public repo, no GitHub account needed); Claude clones it, runs `scripts/instalar.py` and
the setup is guided, in Portuguese or English. One account runs on one PC only.
