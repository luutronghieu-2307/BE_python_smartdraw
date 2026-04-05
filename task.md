Giai đoạn 1: Infrastructure & Environment Setup
[X] Task 1.1: Khởi tạo môi trường ảo (Virtual Environment) và cài đặt các thư viện phiên bản ổn định (n-1): vidgear, ultralytics, torch, torchvision, fastapi, uvicorn.

[X] Task 1.2: Kiểm tra kết nối RTSP từ Camera Yoosee bằng phần mềm bên thứ ba (như VLC) để xác định đúng URL format và độ ổn định của luồng.

[X] Task 1.3: Thiết lập cấu trúc thư mục dự án (Project Structure) theo chuẩn chuyên nghiệp (tách biệt thư mục models/, src/, api/).

Giai đoạn 2: Core Video Processing (VidGear)
[X] Task 2.1: Triển khai hàm initialize_vidgear_stream để kết nối tới Camera. Cấu hình các tùy chọn tối ưu hóa luồng (UDP transport, Low latency mode).UDP

[X] Task 2.2: Xây dựng cơ chế Auto-Reconnect trong trường hợp Camera bị mất mạng hoặc mất nguồn đột ngột.

[X] Task 2.3: Kiểm tra tốc độ đọc Frame (FPS) và độ trễ (Latency) để đảm bảo AI nhận được hình ảnh mới nhất.
X
Giai đoạn 3: AI Engine Integration (YOLOv8 & MobileNetV2)
[X] Task 3.1: Viết hàm load_detection_model để nạp file .pt của YOLOv8. Kiểm tra khả năng chạy trên GPU (CUDA) để tăng tốc.

[X] Task 3.2: Khởi tạo cấu trúc MobileNetV2 và nạp trọng số từ file .pth. Thiết lập chế độ eval() cho model.

[X] Task 3.3: Xây dựng hàm preprocess_classification_input để thực hiện Resize và Normalize ảnh theo chuẩn của PyTorch trước khi đưa vào MobileNetV2.

Giai đoạn 4: Core Logic & Pipeline
[X] Task 4.1: Triển khai hàm execute_inference_pipeline:

Chạy YOLOv8 để lấy Bounding Box.

Thực hiện Crop vùng ảnh đối tượng (ROI).

Đưa vùng ảnh vào MobileNetV2 để phân loại chi tiết.

[ ] Task 4.2: Tối ưu hóa bộ nhớ (Memory Management) khi chạy hai model song song để tránh hiện tượng tràn RAM/VRAM.

Giai đoạn 5: Web API & Auto-Swagger (FastAPI)
[ ] Task 5.1: Khởi tạo FastAPI App và cấu hình Metadata cho Swagger (Title, Description, Version).

[ ] Task 5.2: Định nghĩa Pydantic Schemas cho dữ liệu Input và Output để Swagger tự động trích xuất tài liệu.

[ ] Task 5.3: Viết API Endpoint nhận ảnh hoặc trả về kết quả JSON từ Pipeline đã xây dựng ở Giai đoạn 4.

Giai đoạn 6: Testing & Optimization
[ ] Task 6.1: Kiểm tra hiệu năng (Benchmark) thời gian xử lý tổng thể của toàn bộ Pipeline (End-to-end latency).

[ ] Task 6.2: Debug các lỗi logic khi có nhiều đối tượng xuất hiện cùng lúc trong một Frame.

[ ] Task 6.3: Hoàn thiện tài liệu hướng dẫn sử dụng API trên giao diện Swagger UI.