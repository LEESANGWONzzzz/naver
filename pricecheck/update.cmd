@echo off
rem Download latest pricecheck files from GitHub (API, no CDN cache)
cd /d "%~dp0"
set BR=claude/affectionate-dijkstra-8vza7e
set API=https://api.github.com/repos/LEESANGWONzzzz/naver/contents/pricecheck
for %%F in (price_check.py parsers.py scan.py fees.py profit.py requirements.txt README.md) do (
  curl -sS -f -H "Accept: application/vnd.github.raw" -o "%%F.new" "%API%/%%F?ref=%BR%" && move /y "%%F.new" "%%F" >NUL && echo updated: %%F
)
curl -sS -f -H "Accept: application/vnd.github.raw" -o "..\CLAUDE.md.new" "https://api.github.com/repos/LEESANGWONzzzz/naver/contents/CLAUDE.md?ref=%BR%" && move /y "..\CLAUDE.md.new" "..\CLAUDE.md" >NUL && echo updated: CLAUDE.md
curl -sS -f -H "Accept: application/vnd.github.raw" -o "..\start_remote.cmd.new" "https://api.github.com/repos/LEESANGWONzzzz/naver/contents/start_remote.cmd?ref=%BR%" && move /y "..\start_remote.cmd.new" "..\start_remote.cmd" >NUL && echo updated: start_remote.cmd
if exist *.new del *.new
echo done.
