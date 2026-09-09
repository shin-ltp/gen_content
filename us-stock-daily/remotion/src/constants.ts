// Fixed episode parameters (keep in sync with prepare_remotion.py)

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

/** fade-in/out pad added BEFORE and AFTER each segment's own time
    (the segment content keeps its full measured duration) */
export const FLIP_FRAMES = 16;

/** transition sting fades (frames) */
export const STING_FADE_IN = 4;
export const STING_FADE_OUT = 30;

/** narration bed music volume */
export const BED_VOLUME = 0.1;
