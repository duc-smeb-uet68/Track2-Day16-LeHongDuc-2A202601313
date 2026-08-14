# Báo cáo benchmark LightGBM trên CPU

- Dataset gồm 284,807 dòng, 30 features và 492 giao dịch gian lận.
- Thời gian load dữ liệu là 2.982 giây; thời gian training là 3.375 giây với best iteration 13.
- AUC-ROC đạt 0.963426 và Accuracy đạt 0.993417 trên tập test.
- F1 đạt 0.314442, Precision đạt 0.191537 và Recall đạt 0.877551.
- Latency dự đoán một dòng (median) là 1.351 ms; p95 là 1.596 ms.
- Batch 1.000 dòng mất median 0.002341 giây.
- Throughput inference đạt 427112.595 dòng/giây trên môi trường CPU đã ghi trong JSON.
