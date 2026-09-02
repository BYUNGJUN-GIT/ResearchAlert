# Research Alert

관심 키워드에 맞는 신규 논문을 매일 텔레그램으로 보내기 위한 프로젝트입니다.

## 1단계: 관심사 설정

`config/keywords.yaml`을 열어 아래 항목을 본인의 연구 주제로 바꾸세요.

- `include_any`: 하나라도 들어가면 후보가 되는 핵심어
- `include_all`: 모두 들어가야 하는 조건 키워드
- `exclude`: 제목·초록에 있으면 제외할 표현
- `excluded_journals`: 수집 대상에서 명시적으로 제외할 저널
- `excluded_publishers`: 출판사 메타데이터를 기준으로 제외할 출판사
- `journals`: `tier_1`부터 순서대로 높은 우선순위를 부여할 저널
- `delivery.max_papers`: 하루 최대 전송 편수

설정에 공백, 중복, 잘못된 자료형이 없는지 아래 명령으로 확인합니다.

```powershell
python -m pip install -r requirements.txt
python src/validate_config.py
```

예상 출력에 `설정이 유효합니다.`가 표시되면 1단계가 완료된 것입니다. 다음 단계에서는 이 파일을 그대로 읽어 OpenAlex/Crossref 및 저널 RSS에서 논문을 수집합니다.

`config/keywords.yaml`에는 비밀 정보가 들어가지 않습니다. 텔레그램 토큰은 다음 단계에서 GitHub Secrets에만 저장합니다.

## 2단계: 신규 논문 후보 수집

OpenAlex의 최근 7일 article 메타데이터를 키워드별로 수집하고, 설정의 제외어·제외 저널·제외 출판사와 저널 우선순위를 적용합니다. 관련 키워드가 제목·초록에서 많이 일치할수록 높은 점수를 받고, 비슷한 관련도에서는 Tier가 높은 저널이 우선합니다.

OpenAlex API 키가 필요합니다. OpenAlex 계정의 [API key settings](https://openalex.org/settings/api)에서 무료 키를 만든 뒤, PowerShell에서 현재 창에만 다음처럼 설정하세요. 키는 코드나 Git에 저장하지 않습니다.

```powershell
$env:OPENALEX_API_KEY = "발급받은_키"
```

한국어 핵심 문장은 Gemini API가 제목·초록 전체를 읽고 새로 작성합니다. Google AI Studio에서 발급한 Gemini API 키를 아래처럼 설정하세요. 무료 티어의 한도 안에서는 별도 비용 없이 사용할 수 있지만, 한도를 넘으면 해당 실행은 실패할 수 있습니다.

```powershell
$env:GEMINI_API_KEY = "발급받은_Gemini_API_키"
```

OpenAlex 반영이 늦을 수 있는 최신 Nature 논문은 공식 Nature RSS를 병행 수집합니다. 현재 Nature, Nature Materials, Nature Physics, Nature Chemistry, Nature Nanotechnology, Nature Energy, Nature Electronics, Nature Photonics, Nature Methods 및 Nature Communications 피드를 설정했습니다.

OpenAlex가 초록을 제공하지 않는 후보는 DOI를 따라 저널 논문 랜딩 페이지의 공개 인용 메타데이터에서 초록을 한 번만 보완 조회합니다. 전문 PDF·유료 본문은 요청하지 않으며, 제목이 관심 키워드와 맞는 후보에만 적용합니다.

점수는 일치한 키워드별 가중치와 저널 tier 가점의 합입니다. `spin` 또는 `magnon`이 들어간 키워드는 20점, 열관리 응용 키워드는 10점, 나머지는 30점입니다. Tier 1/2/3/4의 가점은 각각 120/90/60/30점입니다.

기본 설정은 Tier 1~3에 지정한 저널만 결과에 포함합니다. 새로운 저널도 탐색하고 싶을 때만 `journal_policy.allow_unlisted_journals`를 `true`로 바꾸세요.

```powershell
python src/collect_papers.py
```

터미널과 Telegram에는 최대 10편의 추천 후보와, 제목·초록 전체를 바탕으로 Gemini가 새로 작성한 한국어 핵심 요약 한 문장이 표시됩니다. 전체 결과는 `data/latest_candidates.json`에 저장됩니다. 이 결과 파일은 임시 실행 결과이므로 Git에 올라가지 않습니다.

매주 월요일 실행은 직전 7일의 논문만 조회하며, 추천 이력은 따로 저장하지 않습니다. 따라서 같은 논문이 다음 주의 날짜 범위에 다시 포함되지 않는 한 재추천되지 않습니다. Telegram 설정 전에는 안전한 미리보기 모드로 실행하세요.

```powershell
python src/daily_alert.py --dry-run
```

실제 전송에는 환경 변수 `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID`가 필요합니다. 토큰을 코드나 Git에 저장하지 마세요.

## 3단계: Telegram과 매일 아침 자동 실행

1. Telegram에서 [@BotFather](https://t.me/BotFather)에게 `/newbot`을 보내 봇을 만들고 토큰을 받습니다.
2. 새 봇을 열어 `/start`를 한 번 보냅니다.
3. 현재 명령 프롬프트에서 토큰을 임시 설정하고 채팅 ID를 찾습니다.

```cmd
set TELEGRAM_BOT_TOKEN=발급받은_봇_토큰
python src\telegram_setup.py
```

표시된 번호가 `TELEGRAM_CHAT_ID`입니다. 로컬 시험 전송은 다음처럼 할 수 있습니다.

```cmd
set TELEGRAM_CHAT_ID=표시된_채팅_ID
python src\daily_alert.py
```

GitHub 저장소에서 **Settings → Secrets and variables → Actions → New repository secret**으로 다음 세 비밀값을 등록합니다.

- `OPENALEX_API_KEY`
- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

`.github/workflows/daily-alert.yml`은 매주 월요일 오전 7:30 KST에 실행됩니다. GitHub의 **Actions → Weekly Research Alert → Run workflow**로 예약 전 수동 시험 실행도 할 수 있습니다.

기본적으로 키워드당 최대 100건씩 3페이지(최대 300건)를 받아 최근 7일의 관련 논문을 놓치지 않게 합니다. 검색 결과 수를 줄여 빠르게 확인하려면 다음처럼 실행합니다.

OpenAlex의 공유 API 한도를 넘지 않도록 요청 사이에 약 2초의 간격을 둡니다. 전체 수집에는 몇 분이 걸릴 수 있으며, 429 응답이 오면 서버가 지정한 시간만큼 기다린 뒤 자동 재시도합니다.

또한 Tier 1·2 저널은 OpenAlex Source ID로 최근 7일 논문을 직접 수집한 후 같은 키워드·제외어 규칙을 적용합니다. Tier는 출판사 전체가 아니라 `keywords.yaml`에 명시한 저널명에만 적용합니다. 따라서 결과가 많은 일반 키워드의 앞쪽 페이지에 해당 논문이 없더라도, 상위 Tier 저널 논문은 후보에서 누락되지 않습니다.

```powershell
python src/collect_papers.py --per-keyword 10
```
