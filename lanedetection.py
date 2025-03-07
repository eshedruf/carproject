import cv2
import numpy as np
import utils

def getLaneCurve(img):
    
    #step 1
    imgThres = utils.thresholding(img)
    
    #step 2
    h, w, c = img.shape
    points = utils.valTrackbars()
    imgWarp = utils.warpImg(imgThres, points, w, h)
    

    cv2.imshow('Threshold', imgThres)
    cv2.imshow("Warp", imgWarp)
    return None

if __name__ == "__main__":
    cap = cv2.VideoCapture("vid1.mp4")
    initialTrackBars = [100, 80, 20, 214]
    utils.initializeTrackbars(initialTrackBars)
    
    fps = cap.get(cv2.CAP_PROP_FPS)  # Get frames per second
    delay = int(200 / fps)  # Convert FPS to milliseconds

    while True:
        success, img = cap.read()
        if not success:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Reset to the first frame if at the end
            continue  # Skip to the next iteration, which will read the first frame again

        img = cv2.resize(img, (640, 380))
        img = cv2.flip(img, 0)  # Flip if needed

        getLaneCurve(img)

        cv2.imshow('Video', img)
        if cv2.waitKey(delay) & 0xFF == ord('q'):  # Press 'q' to exit
            break

    cap.release()
    cv2.destroyAllWindows()
