# anti-code-slop

> **AI가 남긴 코드 슬롭을 찾고, 맡긴 범위 안에서만 고치고, 완료 여부를 산문이 아니라 스크립트의 종료 코드로 판정하는 에이전트 스킬입니다.**
>
> 배포 버전 **1.2.0** · Python 3 표준 라이브러리만 사용 · Claude Code와 Codex 프로젝트 스킬용 폴더 패키지 · MIT

## 해결하려는 문제

에이전트에게 "정리해 줘"를 맡기면 다음이 되풀이됩니다.

- 린트 경고를 고치지 않고 `# noqa`, `#[allow(...)]`, `// eslint-disable-next-line`로 덮습니다.
- 예외를 `except Exception: pass`로 삼키고, 실패하는 테스트 앞에 `sleep`을 넣습니다.
- 지운 줄 대신 주석 처리된 코드, `// ===== Helpers =====` 같은 배너, "임시로", "for now" 같은 변명 주석이 남습니다.
- 파일이 그대로인지 확인하려고 sha256 digest를 만들어 적어 두고 다시 계산해 맞춰 봅니다. `git diff --quiet`나 `cmp` 한 줄이면 되는 일입니다.
- "정리했습니다"라는 보고와 실제 결과가 다릅니다. 테스트를 약하게 고쳐 통과시키거나, 맡기지 않은 파일까지 건드립니다.

anti-code-slop은 이 문제를 **결정론 판정**과 **읽기 전용 검토자**로 나눠 풉니다.

| 부분 | 하는 일 |
|---|---|
| `scripts/slop_scan.py`, `scripts/rules.json` | 언어별 어휘 분석으로 슬롭 신호를 찾습니다. 같은 입력이면 어느 환경에서나 같은 결과입니다. Python, Rust, JavaScript/TypeScript, 셸, 산문(`.md` 등)을 다룹니다. `rules.json`의 `reviewers`가 어느 검토자를 언제 부를지 선언합니다 |
| `scripts/slop_gate.py` | `scan`, `snapshot`, `verify`, `restore`. 수정 전후를 비교해 V1~V8을 판정하고 `COMPLETE`(종료 0) 또는 `INCOMPLETE`(종료 1)를 냅니다 |
| `references/` | 주석·구조·산문·무결성 검토자의 역할 지침(판정 기준의 정본), 보고서 형식, 출처 기록 |
| `SKILL.md` | 에이전트가 읽는 절차서. 입력, 수정 유형과 검토자 표, 절차 8단계, 판정 기준, 반환 형식. 판정 기준의 세부는 references로 보냅니다 |

판정이 막는 것: 허용 경로 밖 수정, 교정 중에 새로 만든 해시 코드, 보호 주석(라이선스 헤더, 공개 API 문서, 이슈 링크) 삭제, 확정 신호 증가, 스캐너 회피 표현, 근거 없는 보존, 동작 검사 실패·약화, 신고 없는 파일 삭제. 자세한 기준은 [SKILL.md](SKILL.md)와 [보고서 형식](references/report-format.md)에 있습니다.

## 요구 사항

- 스킬 실행: Python 3(표준 라이브러리만). Python 3.12.3에서 시험했습니다. `snapshot`과 `verify`는 같은 인터프리터로 돌립니다.
- 대상의 동작 검사: 호출자가 `--check`로 주는 명령에 필요한 도구.
- 이 패키지의 회귀 시험 전체: 위에 더해 `cargo`(오프라인 빌드 가능), `node`(`node --test`), `bash`. cargo가 없으면 fixture 판정 시험 일부가 건너뛰어지고, 필수 시험 검사(`tests/required_tests.py`)가 그것을 실패로 보고합니다.

## 설치

스킬 폴더 하나를 프로젝트의 스킬 발견 자리에 그대로 둡니다. 설정 파일이나 훅은 쓰지 않습니다.

| 하네스 | 자리 |
|---|---|
| Claude Code | `<프로젝트>/.claude/skills/anti-code-slop/` (또는 사용자 전역 `~/.claude/skills/anti-code-slop/`) |
| Codex | `<프로젝트>/.agents/skills/anti-code-slop/` |

```bash
# 저장소에서 (예: Claude Code)
git clone --branch v1.2.0 <이 저장소 URL> .claude/skills/anti-code-slop

# 또는 태그 아카이브로
mkdir -p .claude/skills/anti-code-slop
git -C <받은 저장소> archive v1.2.0 | tar -x -C .claude/skills/anti-code-slop

# 설치본 확인: clone으로 받았으면 git으로 (빈 출력, 그리고 v1.2.0)
git -C .claude/skills/anti-code-slop status --porcelain
git -C .claude/skills/anti-code-slop describe --tags --exact-match

# 설치본 확인: 아카이브로 받았으면 받은 저장소의 태그와 바이트를 직접 비교
python3 -B .claude/skills/anti-code-slop/tools/package_manifest.py --check \
  --root .claude/skills/anti-code-slop --against <받은 저장소> --ref v1.2.0
```

`PACKAGE_MANIFEST.json`은 패키지를 이루는 파일의 목록·크기·모드만 적습니다. digest는 적지 않습니다. 파일이 그대로인지는 git이나 태그 blob과의 직접 비교로 확인합니다(`references/integrity-review.md` 규칙 2·3).

두 하네스를 함께 쓰면 한 자리에 두고 다른 자리는 심볼릭 링크로 가리키면 됩니다. 두 자리에 실제 복사본을 따로 두면, 실행하지 않은 쪽 복사본은 프로젝트의 일부로 스캔됩니다.

프로젝트 안에 설치해도 스캐너는 **설치된 스킬 폴더를 스캔하지 않습니다**(해시는 하므로 실수로 바꾸면 V1이 잡습니다). 스킬의 시험 fixture에 일부러 넣은 슬롭이 프로젝트의 슬롭으로 세어지지 않습니다.

## run 폴더

판정 기록(스냅숏, 스캔, 검토, 보고서, 판정, 백업)은 대상 밖의 run 폴더에 남습니다. 대상 안의 run 폴더는 거절합니다.

- `--run-dir <경로>`를 주면 그곳을 씁니다.
- 주지 않으면 `$ANTI_CODE_SLOP_RUNS/<대상명>-<시각>/`, 환경 변수가 없으면 `${XDG_STATE_HOME:-~/.local/state}/anti-code-slop/runs/<대상명>-<시각>/`입니다. `snapshot`이 출력하는 `run_dir`를 이후 `verify`, `restore`에 그대로 씁니다.
- 하네스 샌드박스가 홈 아래 쓰기를 막으면(예: Codex `workspace-write`) 허용된 곳(`/tmp` 등)을 `--run-dir`나 `ANTI_CODE_SLOP_RUNS`로 지정합니다. 대상 프로젝트 안은 안 됩니다.

## 사용

에이전트에게 대상, 수정 허용 경로, 허용 수정 유형, 동작 검사를 알려 주고 이 스킬로 처리하라고 하면 됩니다. 허용 경로를 주지 않으면 감사만 하고 파일을 하나도 바꾸지 않습니다.

아래는 사용 흐름을 설명하는 **예시 대화이며 실제 실행 기록은 아닙니다.**

> **사용자**: anti-code-slop으로 `src/`의 억제 주석과 주석 처리된 코드를 정리해 줘. 테스트는 `pytest -q`야. `tests/`는 건드리지 마.
>
> **에이전트**: `snapshot --target . --allowed src --fix-types lint-suppression commented-code --check 'pytest -q'`로 기준을 남겼습니다(기준 검사 통과, `tests/`는 허용 경로 밖이라 바뀌면 V1이 잡습니다). 주석·구조 검토자를 새 맥락으로 띄워 신호 14건을 판정받고, `src/` 안에서 11건을 고쳤습니다. 스타일 전용 억제 2건은 근거를 붙여 보존했고, 공개 API를 바꿔야 하는 1건은 `blocked`로 남겼습니다. `verify` 결과는 `INCOMPLETE`(V3: `blocked` 1건)입니다. 그 1건은 제안으로 보고합니다.

직접 돌려 보려면:

```bash
SKILL=.claude/skills/anti-code-slop
python3 $SKILL/scripts/slop_gate.py scan --target . --out /tmp/slop-scan.json   # 읽기 전용 감사
```

전체 절차(스냅숏 → 검토 → 검수 → 수정 → 수정 후 검토 → 보고서 → 판정 → 되돌림)는 [SKILL.md](SKILL.md)에 있습니다.

## 한계

- `COMPLETE`는 이번 호출의 범위와 판정 항목 V1~V8에 대한 완료입니다. 의미상 정답성, 성능, 배포를 뜻하지 않습니다.
- 휴리스틱 신호(변명 주석, 제약 주석, 타이머 우회, 산문 상투구)의 판정 내용이 옳은지는 스크립트가 판정하지 않습니다. 판정이 있는지만 봅니다.
- 동작 검사의 결과는 환경(도구 설치, 네트워크)에 따라 달라질 수 있습니다. 슬롭 판정 자체는 외부 도구와 무관합니다.
- 규칙이 없는 언어의 파일은 "검사하지 않은 파일"로 보고만 됩니다.
- `rules.json`의 `manual_ref`는 비공개 내부 매뉴얼의 절 번호이며 출처 표시입니다. 판정에 쓰이지 않습니다.

## 패키지 검증(배포자용)

패키지 루트에서:

```bash
python3 -B tools/sanitize_check.py                         # SANITIZE OK (0 hits)
python3 -B -m unittest discover -s tests -v 2>&1 | tee /tmp/slop-tests.txt
python3 -B tests/required_tests.py < /tmp/slop-tests.txt   # required tests: all present and ok
python3 -B tools/smoke_install.py                          # 마지막 줄 SMOKE-PASS
python3 -B tools/package_manifest.py --check               # MANIFEST OK
```

`smoke_install.py`는 임시 프로젝트의 `.claude/skills/`와 `.agents/skills/`에 각각 설치해 설치본을 manifest 목록과 패키지 바이트로 직접 비교하고(digest 없음, 태그의 archive 설치는 `--against`로 한 번), 프로젝트 루트 전체를 감사하고, 주석 처리된 코드를 지운 뒤 `verify` `COMPLETE`, `restore`로 원래 파일 복구까지 확인합니다. 임시 폴더 밖에는 쓰지 않습니다. 파일을 바꾸면 `python3 -B tools/package_manifest.py`로 manifest를 다시 씁니다.

위생 검사는 파일 내용만 봅니다. git 커밋 작성자 정보는 검사하지 않으니 공개 전에 `git log --format='%an <%ae>'`로 확인하세요.

## 라이선스와 출처

MIT. pstack(Lauren Tan, MIT)에서 가져와 바꾼 절차와 규칙이 있으며, 원 라이선스 고지는 [LICENSE](LICENSE)에, 무엇을 가져와 어떻게 바꿨는지는 [적용 기록](references/adaptation.md)에 있습니다.
