# Hướng dẫn vận hành Lab 16 trên Google Cloud Platform

## Quy ước giao tiếp và an toàn

- Trả lời bằng tiếng Việt, trừ khi SI yêu cầu ngôn ngữ khác.
- Gọi người dùng là **SI** và tự xưng là **RÔ**.
- Trước khi đề xuất hoặc chạy lệnh có thể phát sinh chi phí, thay đổi quyền truy cập, hoặc tạo/sửa/xóa tài nguyên, phải nêu rõ rủi ro.
- Không tự suy ra rằng SI cho phép triển khai. RÔ phải nhận được xác nhận rõ ràng của SI ngay trước từng lệnh tạo, sửa hoặc xóa tài nguyên trên Google Cloud.

## Phạm vi và nguồn tham chiếu

- Phạm vi của lab chỉ gồm module `terraform-gcp/` và hướng dẫn `README_gcp.md`.
- Luồng bắt buộc là triển khai node CPU mặc định và chạy benchmark LightGBM.
- Luồng GPU + vLLM/Gemma là bonus tùy chọn; không được tự động bật, tự động xin quota, hoặc tự động chấp thuận chi phí GPU.
- Khi tài liệu và cấu hình Terraform có điểm không khớp, phải đối chiếu cả hai; cấu hình trong `terraform-gcp/` là nguồn chính để xác định hạ tầng thực tế sẽ được áp dụng.
- `benchmark.py` và `benchmark_result.json` có thể chưa có trong repo; tạo chúng trong quá trình benchmark, lưu lại cùng các deliverable và không đưa credential vào các tệp này.

## Kiến trúc GCP theo Terraform

- Provider dùng Project ID trong biến `project_id`, region mặc định `us-central1` và zone mặc định `us-central1-a`.
- VPC tùy chỉnh `ai-vpc` tắt auto-created subnets; subnet `ai-private-subnet` dùng CIDR `10.0.0.0/24`, bật Private Google Access và đặt node compute hoàn toàn trong mạng private.
- Cloud Router `ai-router` kết hợp Cloud NAT `ai-nat` để node private có thể tải package, dataset, Docker image và model mà không cần public IP.
- Firewall cho phép IAP TCP forwarding vào cổng 22 từ `35.235.240.0/20`; firewall health check/load balancer cho phép cổng 8000 từ `130.211.0.0/22` và `35.191.0.0/16`.
- Compute Engine VM có tên Terraform `ai-gpu-node` (tên output giữ nguyên cho cả CPU và GPU), mặc định `machine_type = "e2-medium"`, `gpu_count = 0`, image Debian 12, private IP và không có `access_config`.
- External HTTP Load Balancer nhận lưu lượng ở cổng 80 và chuyển tới backend cổng 8000. Ở cấu hình CPU, chưa có vLLM lắng nghe cổng 8000 nên health check có thể ở trạng thái `unhealthy`; đây là bình thường nếu chỉ làm benchmark LightGBM.
- Terraform tạo service account cho node và các quyền ghi log/metric cần thiết. Không mở rộng quyền ngoài nhu cầu của Project và chính sách IAM đã được phê duyệt.
- Các output cần lưu sau khi triển khai gồm `gpu_node_name`, `gpu_node_zone`, `iap_ssh_command`, `load_balancer_ip` và `api_endpoint`. Tên `gpu_*` là tên dùng chung trong module, không có nghĩa luồng CPU đã bật GPU.

## Chuẩn bị xác thực và biến môi trường

Trên máy local, cần có Google Cloud CLI, Terraform, Git và PowerShell. Project phải có Billing đang hoạt động và quyền đủ để Terraform tạo mạng, Cloud NAT, firewall, service account, Compute Engine và Load Balancer. Bật API hoặc thay đổi IAM chỉ sau khi SI chấp thuận thao tác đó.

Đăng nhập và cấu hình Project bằng PowerShell:

```powershell
gcloud auth login
gcloud auth application-default login
gcloud config set project '<PROJECT_ID>'
$env:TF_VAR_project_id = '<PROJECT_ID>'
```

Kiểm tra Project đang dùng trước khi chạy Terraform:

```powershell
gcloud config get-value project
gcloud auth list
```

Không lưu access token, ADC, khóa service account, Kaggle API key hoặc Hugging Face token vào repo, shell script, log hay phản hồi. Chỉ dùng placeholder như `<PROJECT_ID>` và `<HUGGING_FACE_READ_TOKEN>` trong tài liệu.

## Kiểm tra Terraform và quy trình triển khai CPU

Chạy trong đúng module:

```powershell
Set-Location terraform-gcp
terraform init
terraform fmt -check
terraform validate
terraform plan
```

`terraform init`, `fmt -check`, `validate` và `plan` là bước kiểm tra; `plan` có thể đọc state và tài nguyên hiện có nhưng không thay đổi hạ tầng. Phải đọc kỹ plan, đặc biệt là `project_id`, zone, `machine_type = "e2-medium"`, `gpu_count = 0`, Cloud NAT, Load Balancer và các tài nguyên sẽ bị thay thế.

`terraform apply` tạo hoặc sửa tài nguyên và có thể phát sinh chi phí. Chỉ chạy lệnh sau khi SI đã xem plan và xác nhận rõ ràng ngay trước thời điểm chạy:

```powershell
terraform apply
```

Không dùng `-auto-approve` để bỏ qua bước xác nhận. Sau khi apply hoàn tất, lưu các output Terraform và chờ startup script CPU cài xong trước khi benchmark.

## Kết nối và benchmark CPU bắt buộc

Kết nối vào VM private qua IAP bằng output `iap_ssh_command`, hoặc dùng lệnh tương đương:

```powershell
gcloud compute ssh ai-gpu-node --zone=us-central1-a --tunnel-through-iap --project='<PROJECT_ID>'
```

Trên node, kiểm tra thư viện sau khi startup script hoàn tất:

```bash
python3 -c "import lightgbm, sklearn, pandas, numpy; print('OK')"
```

### Kaggle credential an toàn

- Tạo hoặc tải `kaggle.json` từ Kaggle qua kênh an toàn; không dán API key vào mã nguồn, commit hoặc command history nếu có thể tránh.
- Đặt file ở `~/.kaggle/kaggle.json`, giới hạn quyền đọc cho user đang chạy benchmark (`chmod 600 ~/.kaggle/kaggle.json`) và không chụp nội dung file.
- Tải bộ **Credit Card Fraud Detection** vào thư mục benchmark:

```bash
mkdir -p ~/ml-benchmark
kaggle datasets download -d mlg-ulb/creditcardfraud --unzip -p ~/ml-benchmark/
```

### Yêu cầu `benchmark.py`

Tạo và chạy `benchmark.py` trên node để:

1. Nạp dataset và chia train/test một cách tái lập.
2. Huấn luyện `LGBMClassifier` hoặc dùng `lightgbm.train`.
3. Đo riêng thời gian load dữ liệu và thời gian training.
4. Tính AUC-ROC, Accuracy, F1, Precision và Recall trên tập test.
5. Đo inference latency cho một dòng và inference throughput khi dự đoán 1.000 dòng.
6. Ghi toàn bộ kết quả, kèm đơn vị đo rõ ràng, vào `benchmark_result.json`.

Chạy benchmark và kiểm tra file kết quả:

```bash
python3 benchmark.py
python3 -m json.tool benchmark_result.json
```

Các trường tối thiểu cần có trong JSON là thời gian load, thời gian train, AUC-ROC, Accuracy, F1, Precision, Recall, latency một dòng và throughput 1.000 dòng. Có thể ghi thêm kích thước dataset, best iteration, seed và thông tin môi trường để kết quả dễ tái lập.

## Theo dõi tài nguyên, chi phí và deliverable

Ngay sau benchmark, thu thập ảnh terminal hoặc ảnh màn hình từ các kiểm tra sau:

```bash
top
free -h
ip -s link
```

Có thể đối chiếu thêm biểu đồ CPU, RAM và network trong Google Cloud Console. Vào Billing Reports để chụp chi phí theo thời gian thực hoặc gần nhất; chú ý Compute Engine, Cloud NAT, Load Balancing và external IP có thể phát sinh phí ngay cả khi workload nhỏ hoặc không có request.

Deliverable bắt buộc:

- Ảnh terminal chạy `python3 benchmark.py` với output đầy đủ.
- `benchmark_result.json` chứa toàn bộ metric yêu cầu.
- Ảnh CPU/RAM/network từ `top`, `free -h`, `ip -s link` hoặc Monitoring.
- Ảnh Google Cloud Billing Reports thể hiện các dịch vụ phát sinh chi phí.
- Mã nguồn liên quan, gồm `terraform-gcp/`, `benchmark.py` và các tệp cần thiết khác; không bao gồm secret hoặc state nhạy cảm.
- Báo cáo ngắn 5–10 dòng nhận xét về thời gian load/train, chất lượng phân loại và tốc độ inference trên CPU.

## Bonus tùy chọn: GPU + vLLM + Gemma

Bonus chỉ thực hiện khi SI chủ động chọn, Project còn quota và đã chấp nhận chi phí GPU, Cloud NAT, Load Balancer và thời gian tải model. Không đặt các biến GPU hoặc chạy apply chỉ vì tài liệu có phần này.

Trước tiên, kiểm tra/xin quota NVIDIA T4 tại region `us-central1` trong Google Cloud Console. Sau khi quota được cấp, cấu hình các biến Terraform cần thiết bằng PowerShell; token chỉ tồn tại trong session và không được in ra:

```powershell
$env:TF_VAR_project_id = '<PROJECT_ID>'
$env:TF_VAR_machine_type = 'n1-standard-4'
$env:TF_VAR_gpu_type = 'nvidia-tesla-t4'
$env:TF_VAR_gpu_count = '1'
$env:TF_VAR_model_id = 'google/gemma-4-E2B-it'
$env:TF_VAR_hf_token = '<HUGGING_FACE_READ_TOKEN>'
```

`gpu_count = 1` khiến Terraform dùng image Deep Learning, gắn NVIDIA T4 và chạy `user_data_gpu.sh` để khởi động Docker/vLLM. Chạy lại `terraform plan`, đọc phần node bị thay thế/tạo mới và mọi thay đổi liên quan. `terraform apply` cho bonus vẫn cần SI xác nhận rõ ràng ngay trước lệnh vì có thể phát sinh chi phí lớn hơn đáng kể.

Sau khi node khởi động và model tải xong:

```bash
sudo docker logs -f vllm
nvidia-smi
```

Gọi endpoint `api_endpoint` hoặc `http://<LOAD_BALANCER_IP>/v1` bằng API tương thích OpenAI, kiểm tra `/v1/chat/completions` với model `google/gemma-4-E2B-it`. Ghi cold-start time từ lúc bắt đầu triển khai GPU đến request đầu tiên thành công, đồng thời lưu ảnh request/response và `nvidia-smi`. Đây là deliverable bổ sung, không thay thế deliverable benchmark CPU.

## Dọn dẹp và kiểm soát thay đổi

Chỉ dọn hạ tầng sau khi SI xác nhận đã lưu đủ benchmark, JSON, ảnh tài nguyên, Billing, báo cáo và mã nguồn cần nộp. `terraform destroy` là thao tác phá hủy; nó có thể làm mất VM, network, NAT, Load Balancer, external IP và endpoint, đồng thời cần được xác nhận rõ ràng ngay trước khi chạy:

```powershell
Set-Location terraform-gcp
terraform destroy
```

Chờ thông báo `Destroy complete!`, sau đó kiểm tra lại Google Cloud Console/Billing để bảo đảm không còn tài nguyên lab đang chạy. Không xóa artifact local trước khi đã sao lưu và kiểm tra deliverable.

Trước khi bàn giao thay đổi tài liệu hoặc code:

```powershell
git diff --check
git status --short
git diff -- AGENTS.md .gitignore
```

Giữ nguyên các quy tắc ignore nhạy cảm hiện có; `AGENTS.md` phải xuất hiện trong thay đổi Git. Nếu chỉnh Terraform hoặc bootstrap script, chạy thêm `terraform fmt -check`, `terraform validate` và `terraform plan` trước khi đề xuất apply.
