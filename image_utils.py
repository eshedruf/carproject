import cv2
import numpy as np

class ImgUtils:
    """Utilities for image thresholding, warping, and resizing."""
    
    @staticmethod
    def threshold(frame):
        """Convert a BGR frame to HSV and apply color thresholding."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.array([125, 50, 50])
        upper = np.array([160, 255, 255])
        return cv2.inRange(hsv, lower, upper)
    
    @staticmethod
    def warp(mask, w_sub=50, h_sub=120):
        """Warp the binary mask to a bird’s-eye view."""
        h, w = mask.shape
        pts1 = np.float32([[w_sub, h - h_sub], [w - w_sub, h - h_sub], [0, h], [w, h]])
        pts2 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
        matrix = cv2.getPerspectiveTransform(pts1, pts2)
        return cv2.warpPerspective(mask, matrix, (w, h))
    
    @staticmethod
    def resize(image, target_w, target_h):
        """Resize image to exactly target_w x target_h (ignores aspect ratio)."""
        return cv2.resize(image, (target_w, target_h))