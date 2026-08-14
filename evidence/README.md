# Minh chứng nộp bài

Thư mục này lưu các ảnh chụp từ lần chạy thật trên GCP:

- `terminal_benchmark.png`: terminal chạy `python3 benchmark.py` và toàn bộ kết quả.
- `resource_usage.png`: CPU/RAM/network từ `top`, `free -h` và `ip -s link`.
- `billing_report.png`: Google Cloud Billing Reports sau khi workload hoàn tất.
- `terraform_destroy.png`: terminal báo `Destroy complete!` sau khi đã lưu đủ bài nộp.

Các tệp `.txt` tương ứng lưu lại output dạng văn bản để có thể kiểm tra metric,
resource usage và kết quả dọn hạ tầng mà không cần đọc dữ liệu từ ảnh.

Ảnh Billing được lọc còn riêng dịch vụ Networking của project lab để không công
khai chi phí của workload không liên quan. Output triển khai được lưu ở
`../terraform_outputs.json`; địa chỉ này ngừng hoạt động sau bước destroy.

Không lưu credential, access token, Project state hoặc nội dung `kaggle.json` trong ảnh.
