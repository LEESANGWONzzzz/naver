@echo off
rem Download latest pricecheck files from GitHub (API, no CDN cache)
cd /d "%~dp0"
set BR=claude/affectionate-dijkstra-8vza7e
set API=https://api.github.com/repos/LEESANGWONzzzz/naver/contents/pricecheck
for %%F in (price_check.py parsers.py fees.py profit.py requirements.txt README.md) do (
  curl -sS -f -H "Accept: application/vnd.github.raw" -o "%%F.new" "%API%/%%F?ref=%BR%" && move /y "%%F.new" "%%F" >NUL && echo updated: %%F
)
if exist *.new del *.new
echo done.
