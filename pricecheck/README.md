# pricecheck — 품번으로 KREAM / POIZON 시세 조회

아울렛에서 품번을 확인하면 집 PC가 크림과 포이즌을 조회하고, 매입가를 넣으면 스마트스토어 순수익까지 계산한다.
아이폰에서는 Remote Control로 명령한다.

> 첫 버전이다. 두 사이트 화면 구조를 미리 확인하지 못했기 때문에, 첫 실행 결과를 보고 고쳐야 한다.
> POIZON은 검색 주소 형식도 확인되지 않아 실패할 가능성이 높다.

## 1단계: PC 설치 (Windows, 한 번만)

1. **Python 설치**: https://www.python.org/downloads/ 에서 설치. 설치 첫 화면에서 **Add python.exe to PATH** 체크.
2. **이 저장소 받기**: GitHub에서 Code → Download ZIP으로 받아 압축을 푼다 (예: `C:\work\naver`).
3. **명령 프롬프트(cmd)** 를 열고:

```
cd C:\work\naver\pricecheck
pip install -r requirements.txt
```

브라우저는 윈도우에 기본으로 깔린 Edge를 쓴다. 별도 브라우저 설치는 필요 없을 것으로 보지만, 실행 시 브라우저 관련 오류가 나면 아래를 한 번 실행:

```
python -m playwright install msedge
```

## 2단계: 조회해 보기

```
run.cmd DD1391-100
run.cmd DD1391-100 --size 270
run.cmd DD1391-100 --size 270 --buy 69000
run.cmd DD1391-100 --only kream
```

- Edge 창이 잠깐 떴다가 닫힌다. 로그인이 필요하다고 나오면 그 창에서 한 번 로그인하면 다음부터 유지된다 (`browser_profile` 폴더에 저장).
- 결과는 화면에 나오고 `results\price_log.csv`에도 누적된다 (엑셀로 열림).
- 매번 `debug` 폴더에 화면 캡처(png)와 페이지 글자(txt)가 저장된다.
  **처음 몇 번은 결과와 이 파일들을 Claude에게 보여줘야 정확하게 고칠 수 있다.**

출력 예시 (형식만 예시, 숫자는 가짜):

```
[KREAM]
  주소: https://kream.co.kr/products/12345?size=270
  품번 일치: 예
  최근 거래가: 129,000원  -> 스마트스토어에서 이 가격에 팔면 순수익 50,000원
  즉시 구매가: 135,000원  -> ...
  즉시 판매가: 120,000원
```

- **품번 일치: 아니오**가 나오면 검색 첫 번째 상품이 다른 상품일 수 있으니 주소를 눌러 직접 확인.
- 순수익은 **스마트스토어 공식** 기준이다 (KREAM/POIZON 판매 수수료는 반영 안 함).

## 3단계: 아이폰에서 명령하기 (Remote Control)

1. **Git for Windows 설치**: https://git-scm.com/download/win (Claude Code가 윈도우에서 사용)
2. **Claude Code 설치**: PowerShell을 열고

```
irm https://claude.ai/install.ps1 | iex
```

3. cmd에서 저장소 폴더로 가서 로그인 후 Remote Control 켜기:

```
cd C:\work\naver
claude
```

처음 한 번 로그인하고 `/exit`로 나온 뒤:

```
claude remote-control
```

4. 아이폰 Claude 앱 → Code 쪽에 이 PC 세션이 보이면 거기서
   "DD1391-100 270 시세, 매입가 69000" 처럼 보내면 된다.

주의:
- 외출 중 PC가 **절전 모드로 들어가지 않게** 설정 (설정 → 시스템 → 전원 → 화면과 절전 → 절전 모드 "안 함").
- Remote Control을 쓸 수 있는 요금제인지, 정확한 메뉴 위치는 공식 문서에서 확인:
  https://code.claude.com/docs
- 설치 명령어가 바뀌었을 수 있으니 안 되면 위 문서의 Windows 설치 안내를 따른다.

## 이용약관

크림, 포이즌이 자동 조회를 허용하는지는 확인하지 못했다.
개인 사입 판단용으로 필요할 때 한 건씩 조회하는 용도로만 쓰고, 대량 반복 조회는 하지 않는다.
