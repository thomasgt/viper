import numpy as np
from PIL import ImageGrab
import cv2
import time
from viper import direct_keys as vk
from viper import interface as vi
from viper import process as vp

# TODO Apply some perspective warping to make lane detection easier
# TODO Come up with a kernel that can find lanes consistently


font = cv2.FONT_HERSHEY_SIMPLEX
startTime = lastTime = currentTime = time.time()
avgFps = 0
avg_threshold = 127
avg_lines = np.zeros((600, 800), dtype=np.uint8)
avg_line_angle = 0

for t in range(5, 0, -1):
    print("Starting in {}...".format(t))
    time.sleep(1)
sp = np.float32([[0, 400], [155, 300], [645, 300], [799, 400]])
ep = np.float32([[250, 599], [250, 500], [550, 500], [550, 599]])
fs = (800, 600)
tm = cv2.getPerspectiveTransform(sp, ep)

# Capture the screen
roi_file = '../data/sanchez1.npz'
try:
    vehicle_data = np.load(roi_file)
    roi_vertices = vehicle_data['roi_vertices']
    #transform_matrix = vehicle_data['transform_matrix']
    #final_size = vehicle_data['final_size']

except IOError:
    screen = cv2.cvtColor(np.array(ImageGrab.grab(bbox=(8, 30, 808, 630))), cv2.COLOR_RGB2BGR)
    roi_vertices = vi.get_roi(cv2.warpPerspective(screen, tm, fs))
    #transform_matrix, final_size = vi.get_perspective_transform(screen)
    #np.savez(roi_file, roi_vertices=roi_vertices, transform_matrix=transform_matrix, final_size=final_size)
    np.savez(roi_file, roi_vertices=roi_vertices)

sp = np.float32([[0, 400], [155, 300], [645, 300], [799, 400]])
ep = np.float32([[250, 599], [250, 500], [550, 500], [550, 599]])
fs = (800, 600)
tm = cv2.getPerspectiveTransform(sp, ep)

forward_control_avg = 0
right_control_avg = 0
left_control_avg = 0
forward_thread = vk.KeyThread(vk.Key.W, 2)
left_thread = vk.KeyThread(vk.Key.A, 0.5)
right_thread = vk.KeyThread(vk.Key.D, 0.5)
forward_thread.start()
left_thread.start()
right_thread.start()
forward_thread.disable()
right_thread.disable()
left_thread.disable()

while True:
    # Capture the screen
    screen = cv2.cvtColor(np.array(ImageGrab.grab(bbox=(8, 30, 808, 630))), cv2.COLOR_RGB2BGR)

    # Apply perspective transform
    screen_transformed = cv2.warpPerspective(screen, tm, fs)

    # Process the image
    screen_gray = cv2.cvtColor(screen_transformed, cv2.COLOR_BGR2GRAY)
    screen_filter = cv2.GaussianBlur(screen_gray, (3, 3), 0)
    # screen_roi_noise = mask_roi_noise(screen_filter, roi_vertices)
    otsu_threshold = cv2.threshold(screen_filter, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[0]
    avg_threshold = 0.6 * avg_threshold + 0.4 * otsu_threshold
    screen_canny = vp.auto_canny(255 - screen_filter, 0.5, avg_threshold)
    screenMask = vp.mask_roi(screen_canny, roi_vertices)

    # Find lines on the image
    lines = cv2.HoughLinesP(screenMask, 1, np.pi / 180, 75, minLineLength=75, maxLineGap=30)
    current_lines = np.zeros_like(screen_gray)
    current_line_angle = 0

    if lines is not None:
        total_length = 0
        for x1, y1, x2, y2 in lines[:, 0, :]:
            if np.abs(y1 - y2) > 0:
                angle = np.arctan((x2 - x1)/(y1 - y2))
                if np.rad2deg(np.abs(angle)) < 70:
                    cv2.line(current_lines, (x1, y1), (x2, y2), 255, 2)
                    cv2.line(screen_transformed, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    current_line_angle += np.arctan((x2 - x1)/(y1 - y2))
                    total_length += np.hypot(x2 - x1, y2 - y1) / 100
        if total_length > 0:
            current_line_angle /= total_length
        else:
            current_line_angle = 0

    avg_lines = 0.5 * avg_lines + 0.5 * current_lines
    avg_line_angle = 0.8 * avg_line_angle + 0.2 * current_line_angle
    cv2.line(screen_transformed, (400, 600), (int(600*np.tan(avg_line_angle) + 400), 0), (0, 255, 0), 2)
    cv2.putText(screen_transformed, "%6.1f" % np.rad2deg(avg_line_angle), (690, 595), font, 1, (0, 255, 0), 2, cv2.LINE_AA)

    # Update controls
    forward_control = 0.5 * np.cos(avg_line_angle) + 0.6
    forward_control_avg = 0.6 * forward_control_avg + 0.4 * forward_control
    if avg_line_angle > 0:
        right_control = 0.7 / (1 + np.exp(-3 * avg_line_angle + 3))
        right_control_avg = 0.7 * right_control_avg + 0.3 * right_control
        left_control_avg = 0
    else:
        left_control = 0.7 / (1 + np.exp(3 * avg_line_angle + 3))
        left_control_avg = 0.7 * left_control_avg + 0.3 * left_control
        right_control_avg = 0
    cv2.putText(screen_transformed, "%0.2f" % forward_control_avg, (720, 395), font, 1, (255, 0, 0), 2, cv2.LINE_AA)
    cv2.putText(screen_transformed, "%0.2f" % right_control_avg, (720, 445), font, 1, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(screen_transformed, "%0.2f" % left_control_avg, (720, 495), font, 1, (0, 0, 255), 2, cv2.LINE_AA)
    forward_thread.set_duty_cycle(forward_control_avg)
    right_thread.set_duty_cycle(right_control_avg)
    left_thread.set_duty_cycle(left_control_avg)

    # Display the processed data
    cv2.imshow("Edge Detected", screen_canny)
    cv2.imshow("Edge Detected + Mask", screenMask)
    cv2.imshow("Hough Lines", avg_lines)
    cv2.imshow("Lanes", screen_transformed)

    # Calculate the frame rate
    currentTime = time.time()
    avgFps = 0.95 * avgFps + 0.05 / (currentTime - lastTime)
    lastTime = currentTime

    # Respond to input
    key_command = cv2.waitKey(1) & 0xFF
    if key_command & 0xFF == ord('q'):
        print("Average FPS: %0.1f" % avgFps)
        break
    elif key_command == ord('s'):
        forward_thread.disable()
        right_thread.disable()
        left_thread.disable()
    elif key_command == ord('g'):
        forward_thread.enable()
        right_thread.enable()
        left_thread.enable()

cv2.destroyAllWindows()
