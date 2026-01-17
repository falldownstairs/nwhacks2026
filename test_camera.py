import cv2

print("Testing camera access...")
print("Available cameras:")

# Try to find working camera
for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            print(f"  Camera {i}: Working! Resolution: {frame.shape}")
            cv2.imshow(f'Camera {i} - Press any key', frame)
            cv2.waitKey(2000)  # Show for 2 seconds
            cv2.destroyAllWindows()
        cap.release()
    else:
        print(f"  Camera {i}: Not available")

print("\nIf you saw a window, your camera is working!")
print("If not, check System Settings → Privacy & Security → Camera")