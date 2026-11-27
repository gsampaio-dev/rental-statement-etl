# Validação da versão 0.3.0

Auditoria local em 26/11/2026, candidata pública `af9fae8`.

| Verificação | Resultado |
| --- | --- |
| Suíte sintética | 64/64 aprovados, zero falhas |
| Build Windows onedir | Concluído |
| Execução do binário | Cinco PDFs sintéticos, três registros, dois itens para revisão e uma cópia ignorada |
| Comparação com 0.2.4 | Dados, tipos e formatos de Excel coincidentes |

Python 3.12.10; Tesseract 5.5.0.20241111. A suíte foi executada com `python -m unittest discover -s tests -v` e o build com `build.ps1`, no ambiente Windows provisionado. CI remoto não executado na ocasião da auditoria. Não repeti a validação histórica em 51 documentos privados.

As capturas representam a janela do executável real, com marca neutra e pasta sintética DEMO. As opções de automação do executável foram usadas para acionar a demonstração; o GIF é uma sequência editorial de estados capturados, com pausas para leitura.

O OCR é acionado quando não há texto nas células extraídas da tabela. Layouts inválidos com texto podem ir diretamente à revisão. O suporte atual é de PDFs de uma página, para as rubricas expressamente suportadas. O extrator ainda não oferece suporte universal. Mantenho os documentos e identificadores privados fora deste showcase. Antes de distribuir o binário, preciso revisar as condições de redistribuição das dependências.
