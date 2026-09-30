# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ. Ba alert dưới đây tương ứng với ba "thất bại" mà người dùng cảm nhận được: chậm, lỗi, hoặc chất lượng trả lời kém. Nguồn số liệu là `data/logs.jsonl` (structured log) và dashboard 6 panel trong [dashboard.yaml](../../config/dashboard.yaml).

Quy ước chung:

- Kênh thông báo: Slack `#k4-l3b-alerts`.
- Alert đã cấu hình trong [alert_rules.yaml](../../config/alert_rules.yaml).

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms` — một nhánh của SLO `fast_successful_requests` (SLI: response_sent với `latency_ms <= 3000`)
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` liên tục trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn ngưỡng cam kết trước khi nhận câu trả lời; tail latency tăng có thể làm SLO cháy error budget
- Ba bước kiểm tra đầu tiên:
  1. Mở panel latency trên dashboard để xác nhận P95/P99 và khoảng thời gian bắt đầu xấu.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh thời gian span retrieval và generation để tìm bước chậm.
- Mitigation tạm thời: nếu span retrieval chậm (vd practice scenario `rag_slow`), tắt scenario bằng `python scripts/inject_incident.py --scenario rag_slow --disable`; nếu do prompt version mới, rollback label `production` về version cũ.
- Owner: `student-2A202602492`

## Alert 2

- Tên: `HighErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: error rate từ cặp event `request_failed` / `request_received` — guardrail `error_rate_pct_max: 2` trong [slo.yaml](../../config/slo.yaml)
- Điều kiện và thời gian duy trì: `error_rate_pct > 2%` liên tục trong 5 phút
- Ảnh hưởng tới người dùng: tỉ lệ request trả HTTP 500 tăng, người dùng không nhận được câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Xem panel errors trên dashboard: tỉ lệ lỗi, phân bố theo `error_type`, thời điểm bắt đầu tăng.
  2. Lọc log `event == "request_failed"` trong khoảng đó, lấy một `correlation_id` và đọc `error_type` cùng `payload.detail`.
  3. Mở trace cùng `correlation_id`, kiểm tra span lỗi (`tool_name`, trạng thái) để xác nhận bước gây lỗi.
- Mitigation tạm thời: nếu là `Vector store timeout` (practice scenario `tool_fail`), tắt bằng `python scripts/inject_incident.py --scenario tool_fail --disable`; nếu lỗi do cấu hình mới, khôi phục cấu hình cũ và thông báo trên kênh Slack.
- Owner: `student-2A202602492`

## Alert 3

- Tên: `RetrievalSuccessDrop`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: tỉ lệ `tool_success == true` trên các `response_sent` — guardrail `retrieval_success_rate_pct_min: 90` trong [slo.yaml](../../config/slo.yaml)
- Điều kiện và thời gian duy trì: `tool_success_rate_pct < 90%` liên tục trong 5 phút
- Ảnh hưởng tới người dùng: retrieval thất bại nghĩa là câu trả lời thiếu context đúng, quality proxy giảm; người dùng nhận được câu trả lời chung chung hoặc sai lệch mà không hề có báo lỗi
- Ba bước kiểm tra đầu tiên:
  1. Xem panel errors (mục retrieval success) và panel quality trên dashboard, xác nhận khoảng thời gian giảm.
  2. Lọc log `event == "response_sent"` có `tool_success == false`, lấy một `correlation_id`.
  3. Mở trace cùng `correlation_id`, kiểm tra span retrieval: trạng thái, thời gian và doc_count để khoanh vùng.
- Mitigation tạm thời: tắt scenario `tool_fail`/`rag_slow` nếu đang bật; kiểm tra lại nguồn tài liệu của RAG; nếu do thay đổi prompt ảnh hưởng truy xuất, rollback label `production`.
- Owner: `student-2A202602492`