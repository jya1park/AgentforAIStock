# Round 1 — manual audit (pre-patcher baseline)

_라운드 1은 patcher 도입 전에 사람이 분석한 결과. 라운드 2부터 patcher가 자동 생성._

## 점수 요약

### stock-analyst (n=10)
| 차원 | 점수 | 비고 |
|---|---|---|
| headline_ticker_mapping | 1.00 | ✅ 직전 패치(`beec46e`) 작동 |
| fg_trend_arithmetic | 1.00 | ✅ 방향·수치 오류 0 |
| three_signal_integration (3-signal) | 0.10 | ❌ 거의 실패 — verdict 부재 |
| hallucination | 0.78 | ⚠️ 절반은 grader false positive (SPY/Capex 등) |
| llm_cross_check_clarity | 2.5/5 | ⚠️ judge도 verdict 부재 일관 지적 |
| llm_evidence_grounding | 3.7/5 | 보통 |
| llm_tone_consistency | 3.0/5 | ⚠️ 감정·예측 표현 |
| llm_thesis_usage | 2.8/5 | ⚠️ emerging_compute·HBM 핵심 누락 |

### chat-assistant (n=30)
| 차원 | 점수 |
|---|---|
| llm_answer_relevance | 3.87/5 |
| llm_grounding | 2.43/5 (context 생략 평가 조건) |
| llm_format | 3.2/5 |
| llm_refusal_appropriateness | 4.6/5 ✅ |

## 결함 패턴

### 1. cross-check verdict 누락 (10/10)
10개 모두 VIX/F&G/곡선을 **3개 분리된 문장**으로 작성, "정렬 vs 충돌" verdict 없음. judge도 일관되게 "verdict 부재" 지적.

### 2. ontology thesis 키워드 누락
"emerging_compute 역상관 (자금 이동 vs 동조)", "HBM 단일 공급원", "800G/1.6T" 같은 핵심 thesis가 분석에서 거의 사용 안 됨.

### 3. tone 감정·예측 표현
"급상승", "주목받고", "기대감 증가", "신중한 접근 필요" 등.

## 인프라 버그 (라운드 1 결과의 노이즈)

| 버그 | 영향 | 수정 |
|---|---|---|
| 시드 페이로드에 Breadth 섹션 누락 | SPY 환각 false flag 4건 | `evals/seeds/payload_baseline.md` Breadth 추가 |
| generator 프롬프트도 Breadth 미포함 | 변형도 Breadth 없음 | `evals/generators.py` 프롬프트 갱신 |
| grader ALLOWED에 ontology 어휘 없음 | Capex/Fabless/Optical 환각 false flag 5+건 | `evals/graders.py` ALLOWED 확장 |
| three_signal_integration grader가 시장 폭 미포함 | 의도와 grader 불일치 | 4-signal partial credit (0.25/signal) |

## 다음 단계

- 라운드 2부터 `python -m evals.auto --start-round 2 --max-rounds 5`로 자동 루프 시작
- patcher가 cross-check #3 verdict 강제·thesis 의무화 패치 제안 예상
- 매 라운드 git commit 자동 → 점수 떨어지면 자동 revert
- 각 라운드 결과는 `evals/patches/round_NNN.md`로 자동 기록
