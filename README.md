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
