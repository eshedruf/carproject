import cv2
import numpy as np

def process_video(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video file:", video_path)
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            # End of video
            break

        # Convert frame to grayscale if needed
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        height, width = gray.shape

        # Divide the frame into left and right halves
        left_half = gray[:, :width // 2]
        right_half = gray[:, width // 2:]

        # Count black pixels (assuming pixel value 0 is black)
        left_black_count = np.sum(left_half == 0)
        right_black_count = np.sum(right_half == 0)

        # Determine which side has more black pixels and print counts
        if right_black_count > left_black_count:
            direction = "right"
        elif left_black_count > right_black_count:
            direction = "left"
        else:
            direction = "equal"

        print(f"Left: {left_black_count} black pixels, Right: {right_black_count} black pixels -> {direction}")

        # Draw a thin vertical line in the middle of the frame
        center_x = width // 2
        # For a grayscale image, color is a scalar. Here we choose 128 as a mid-gray value.
        cv2.line(gray, (center_x, 0), (center_x, height), 128, 1)

        # Display the frame with the drawn line (optional)
        cv2.imshow("Processed Frame", gray)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    video_path = "warp.mp4"  # Change to your video file if needed.
    process_video(video_path)
