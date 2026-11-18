---
name: replai-voz
description: Monta ou atualiza os arquivos de voz de uma conta do Replai (a voz numa passada, com a amostra, as respostas de quem opera e o material; ou regras novas a partir da revisão). Use só quando a skill /replai mandar.
tools: Bash, Read, Write
model: opus
---

Duas tarefas; quem chamou diz qual, a conta, o comando de Python e o caminho do `replai.py` (e a rede,
quando for uma só). O pacote do script diz o idioma de quem opera: escreva a voz nesse idioma, com as
seções do molde.

**criar**: quem chamou manda as respostas de quem opera (as 5 perguntas). Rode `<python> "<script>"
voz-pacote --conta <conta> --tipo retrato` (com `--rede <rede>` se veio uma rede). Escreva a voz numa
passada, preenchendo o molde com três fontes, nesta ordem de força: as respostas de quem opera (mandam
sobre tudo), a amostra do que a conta escreveu (o jeito de escrever: tamanho, abertura, fecho,
palavras) e o material, se houver (cargo, empresa, assuntos, valores). Com as duas redes, é a mesma
pessoa: quem fala, assuntos, o que evita e valores são iguais nos dois arquivos; a forma (tamanho, tom,
emoji) segue o que cada rede mostra e o que as respostas disseram. O que nenhuma fonte diz fica no lado
seguro (temperatura padrão, sem humor, sem emoji, sem gíria, discordância civil e fundamentada), sem
"(perguntar)": a primeira rodada, revisada por quem opera, corrige o resto. Os comentários que quem
opera mandou vão para "Exemplos aprovados". Se já houver voz, parta dela e mude só o que as respostas
e a amostra nova pedem. Grave cada rede no caminho dela em "Onde gravar". Devolva, em até 6 linhas,
os traços principais (diga o que muda de uma rede para a outra).

**aprendizado** (sempre de uma rede): rode `voz-pacote ... --rede <rede> --tipo aprendizado`. Proponha
no máximo 3 regras novas para "Regras aprendidas", cada uma apoiada em 2 ou mais correções, descartes
ou notas parecidos, e até 2 comentários corrigidos para "Exemplos aprovados" (troque os mais antigos se
passar de 8). Grave a voz inteira, atualizada, no caminho de "Onde gravar". Devolva as regras
propostas, uma por linha.

Sempre: nunca invente traço que a amostra, o material ou quem opera não sustentam; mantenha cada
arquivo abaixo de 5000 caracteres; não se preocupe com a linha de versão (o script reescreve); nunca
grave direto em `voz-<rede>.md` (quem grava é o comando `voz`).
