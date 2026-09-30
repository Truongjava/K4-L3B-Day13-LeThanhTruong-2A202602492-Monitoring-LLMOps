# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Lê Thanh Trường
- **MSSV:** 2A202602492
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/Truongjava/K4-L3B-Day13-LeThanhTruong-2A202602492-Monitoring-LLMOps
- **Commit SHA cuối:**
- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-<MSSV>`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.txt` |
| Log validator | `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.txt` |
| PII redaction | `evidence/05-pii-redaction.txt` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt promote | `evidence/10a-prompt-promote.png` |
| Prompt rollback | `evidence/10b-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | **100/100** | Baseline fail correlation ID + enrichment; sau khi hoàn thiện middleware, bind context, scrub processor thì đạt tuyệt đối |
| `validate_dashboard.py` | 6/6 | **6/6** | Contract 6 panel không đổi giữa hai lần chạy |
| `pytest` | 22 passed | **26 passed** | Thêm 4 test PII (CCCD, thẻ, passport, địa chỉ) |
| Số traces hợp lệ | 0 | (bạn ghi số đếm thật từ Langfuse) | ≥10, đủ root/retrieval/generation |
| Số PII leak | 0 | **0** | Validator dùng regex độc lập để rà `data/logs.jsonl` |
| Latency P95 / TTFT P95 | (chưa đo) | **1411ms / 50ms** | P95 bị kéo bởi request cold start lần đầu (fetch prompt); request ổn định ~159ms |
| Retrieval success rate | (chưa đo) | **100%** | Chưa bật incident nào trong lần chạy cuối |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` (app/middleware.py) xóa context cũ bằng `clear_contextvars()` ở đầu mỗi request; nhận `x-request-id` từ header hoặc tự sinh `req-<8-hex>` bằng `uuid.uuid4().hex[:8]`; bind vào structlog contextvars, lưu vào `request.state` và ghi ID + thời gian xử lý vào response headers `x-request-id` / `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** trước log `request_received`, `app/main.py` bind `user_id_hash` (SHA-256 12 ký tự đầu, không lưu user_id gốc), `session_id`, `feature`, `model`, `env`, cùng `correlation_id`; nhờ `merge_contextvars`, mọi dòng log trong request đều mang đủ các trường này.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` (app/logging_config.py) được đặt **trước** `JsonlFileProcessor`/`JSONRenderer` nên mọi chuỗi (payload, event, contextvars, error detail) được chạy `scrub_text` trước khi serialize/ghi file. `scrub_text` (app/pii.py) redact email, điện thoại VN, CCCD, thẻ thanh toán, passport và địa chỉ VN thành `[REDACTED_<TYPE>]`.
- **Cách kiểm chứng kết quả:** chạy `python scripts/validate_logs.py` trên `data/logs.jsonl` — validator dùng regex riêng để phát hiện PII nguyên văn độc lập với code scrub của học viên; kết quả cần ≥ 80/100.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** mọi trace nằm trong project Langfuse `day13-k4-l3b-<MSSV>` do tôi tự tạo; tôi tự chạy `scripts/load_test.py` để sinh trace, mỗi trace có tag chứa feature và model của chính app tôi chạy.
- **Cấu trúc root/retrieval/generation observations:** root là observation `day13-agent-request`/`lab-agent-run` (as_type=agent, decorator `@observe`). Trong `LabAgent.run`, dùng `start_as_current_observation` (SDK v4) để tạo child observation: `retrieval` (as_type=retriever) cho `retrieve()` và `llm-generate` (as_type=generation, có model, prompt, input/output đã scrub) cho `FakeLLM.generate()`; generation được `.update()` thêm `usage_details` (prompt/completion tokens), `cost_details` (input/output/total cost) và `ttft_ms`.
- **Cách nối trace với log:** `correlation_id` được ghi vào trace metadata của cả root và child observations; log cùng request cũng mang `correlation_id` đó, nên lọc log → lấy ID → tìm trace cùng ID.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** (bạn điền theo project của mình)
- **Version/label candidate:** (bạn điền)
- **Trace ID của mỗi version:** (bạn điền)
- **Cách promote và rollback `production`:** đổi label `production` trên Langfuse UI (không sửa code) — promote khi gắn label sang version mới, rollback khi gắn lại về version cũ; app đọc prompt theo name + label từ `.env` nên không cần thay đổi source.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `config/dashboard.yaml` định nghĩa 6 panel — latency (P50/P95/P99 + TTFT), traffic, errors (error rate + retrieval success), cost, tokens, quality — mỗi panel có nguồn `data/logs.jsonl`, unit, thời gian 60 phút, refresh 15–30s và threshold; đã đạt validator 6/6.
- **SLO và lý do chọn:** SLO `fast_successful_requests` (config/slo.yaml): ≥ 99.5% request trong cửa sổ 28 ngày có `response_sent` với `latency_ms <= 3000` — phản ánh đúng hai thứ người dùng cảm nhận: có câu trả lời và trả lời đủ nhanh.
- **Cách tính error budget:** error budget = 100% − SLO = 0.5%/28 ngày. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng; guardrail phụ: error rate ≤ 2%, cost ≤ 2.5 USD/ngày, quality ≥ 0.75, retrieval success ≥ 90%.
- **Ba alert và runbook tương ứng:** config/alert_rules.yaml — `HighLatencyP95` (warning, p95 > 3000ms trong 5m), `HighErrorRate` (critical, error rate > 2% trong 5m), `RetrievalSuccessDrop` (critical, tool_success < 90% trong 5m); cả ba gửi Slack `#k4-l3b-alerts` và có runbook tại docs/alerts.md với ba bước kiểm tra: xem dashboard → lọc log lấy `correlation_id` → mở trace so sánh span.

> Ví dụ cách viết error budget: "SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO."

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** 10:31:52 → 10:32:03 UTC (5 request feature=monitoring bắn liên tiếp bằng `--challenge --concurrency 5`)
- **Triệu chứng từ metrics:** panel Latency của dashboard nhảy từ P95 ~160ms lên **~2653ms** đúng phút 10:31 (evidence 12); cả 5 request đều vượt `latency_threshold_ms=2000` của challenge. Client-side còn tệ hơn (8–13s) vì `retrieve()` đồng bộ chặn event loop khi chạy 5 request đồng thời.
- **Log line và correlation ID liên quan:** lọc `data/logs.jsonl` lấy `event=response_sent`, `feature=monitoring`, `latency_ms>2000` được đúng 5 dòng; đại diện là **`correlation_id=req-8006e6dd`** với `latency_ms=2652` (evidence 13).
- **Trace ID và span gây ảnh hưởng:** mở trace cùng `correlation_id=req-8006e6dd` trên Langfuse → span **retrieval** chiếm ~2.5s (gần toàn bộ thời gian request), span **llm-generate** chỉ ~150ms → span retrieval là thủ phạm (evidence 14).
- **Root cause:** incident `rag_slow` đang được bật — mock retrieval thêm `time.sleep(2.5)` mỗi lần gọi, đúng khớp với span retrieval ~2.5s trong trace; chỉ các request đi qua bước retrieval bị ảnh hưởng.
- **Fix action:** tắt incident (`POST /incidents/rag_slow/disable`); chạy lại cùng workload challenge `--concurrency 5` → latency client-side về **640–800ms**, server-side P95 về ~160ms (dashboard hiện hồi phục ở phút 10:32 ngay sau spike).
- **Preventive measure:** alert `HighLatencyP95` đã có runbook (docs/alerts.md#alert-1) — theo dõi latency P95 từng phút, lọc log lấy correlation ID, mở trace so sánh span trước khi escalate; kèm kiểm tra trạng thái incident qua `GET /health` (trả `incidents: {rag_slow: false}` sau khi xử lý).

> Gợi ý cách viết ngắn, không thay cho evidence thực tế: "Metric cho thấy `[latency/error/cost/quality]` bất thường trong `[khoảng thời gian]`. Log line `[event]` có `correlation_id=[...]` đại diện cho request bị ảnh hưởng. Trace cùng `correlation_id` cho thấy span `[retrieval/generation/prompt/tool]` có dấu hiệu `[chậm/lỗi/token tăng]`. Root cause là `[nguyên nhân suy ra từ evidence]`. Fix action là `[hành động khôi phục]`; preventive measure là `[alert/runbook/test/guardrail để ngăn tái diễn]`."

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:**
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
