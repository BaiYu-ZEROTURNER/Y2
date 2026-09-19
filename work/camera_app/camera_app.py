import cv2

# 打开摄像头（0 表示默认摄像头）
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()   # 读取一帧
    if not ret:
        break
    
    cv2.imshow("Camera", frame)   # 显示画面
    
    # 按 0 键退出
    if cv2.waitKey(1) & 0xFF == ord('0'):
        break

# 释放资源
cap.release()
cv2.destroyAllWindows()