import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  random,
  staticFile,
  useCurrentFrame,
} from "remotion";
import {
  FLIP_FRAMES,
  HEIGHT,
  STING_FADE_IN,
  STING_FADE_OUT,
  WIDTH,
} from "./constants";
import { EndCard } from "./EndCard";
import { EpisodeInput, SegmentInput } from "./types";

// B1-B4 corner pages share the same slide chrome/background. Transitions
// inside a group must not fade the whole page; overlapping two full-slide
// screenshots keeps identical pixels (logo, photos, layout) mathematically
// still while only the changed region visibly dissolves.
const CORNER_GROUP_SLIDES: Record<string, string[]> = {
  B1: ["s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"],
  B2: ["s13", "s14", "s15", "s16", "s17", "s18", "s19", "s20"],
  B3: ["s21", "s22", "s23", "s24", "s25", "s26", "s27", "s28"],
  B4: ["s29", "s30", "s31", "s32", "s33", "s34", "s35"],
};

const stateKeyOf = (seg: SegmentInput): string =>
  seg.stateKey ?? seg.image ?? `__no_image__:${seg.id}`;

const cornerGroupOf = (seg: SegmentInput): string | null => {
  if (!seg.slide) return null;
  for (const [group, slides] of Object.entries(CORNER_GROUP_SLIDES)) {
    if (slides.includes(seg.slide)) return group;
  }
  return null;
};

const sameVisualGroup = (a: SegmentInput, b: SegmentInput): boolean => {
  if (!a.slide || !b.slide) return false;
  if (a.slide === b.slide) return true;
  const group = cornerGroupOf(a);
  return group !== null && group === cornerGroupOf(b);
};

type PixelTransitionKind = "content" | "page";

const transitionKindFromPrevious = (
  current: SegmentInput,
  prev: SegmentInput | undefined,
): PixelTransitionKind | null => {
  if (!prev?.image) return null;
  if (
    sameVisualGroup(prev, current) &&
    stateKeyOf(prev) === stateKeyOf(current)
  ) {
    return null;
  }
  return sameVisualGroup(prev, current) ? "content" : "page";
};

export const segmentFrames = (seg: SegmentInput, fps: number): number =>
  Math.max(1, Math.round(seg.durationSec * fps));

/** Narration waits until the transition ends, then leaves a 1s breath. */
export const stingPadFrames = (
  seg: SegmentInput,
  fps: number,
  stingFrames?: number,
): number => (seg.sting ? Math.round(stingFrames ?? 180) + fps : 0);

export const slotFrames = (
  seg: SegmentInput,
  fps: number,
  stingFrames?: number,
): number =>
  segmentFrames(seg, fps) + 2 * FLIP_FRAMES + stingPadFrames(seg, fps, stingFrames);

export const totalFramesOf = (
  segments: SegmentInput[],
  fps: number,
  stingFrames?: number,
): number =>
  segments.reduce((acc, s) => acc + slotFrames(s, fps, stingFrames), 0);

const SlotImage: React.FC<{
  seg: SegmentInput;
  opacity: number;
}> = ({ seg, opacity }) =>
  seg.image ? (
    <AbsoluteFill style={{ opacity }}>
      <Img src={staticFile(seg.image)} width={1920} height={1080} />
    </AbsoluteFill>
  ) : null;

// Pixel-dissolve transition. The outgoing slide is cut into square blocks;
// each block holds until its own threshold, then fades out quickly. The
// threshold blends a center-out radial sweep with deterministic randomness,
// so the mosaic expands outward with a noisy pixel edge instead of a flat
// opacity fade. Blocks vanishing over unchanged pixels reveal identical
// content underneath, keeping shared chrome and photos perfectly still.
const BLOCK_FADE_FRAMES = 4;
const STAGGER_FRAMES = FLIP_FRAMES - BLOCK_FADE_FRAMES;
const RADIAL_WEIGHT = 0.6;
const RANDOM_WEIGHT = 0.4;

const PixelTransitionOverlay: React.FC<{
  seg: SegmentInput;
  seed: string;
  blockSize: number;
}> = ({ seg, seed, blockSize }) => {
  const frame = useCurrentFrame();
  if (frame >= FLIP_FRAMES || !seg.image) return null;

  const cols = WIDTH / blockSize;
  const rows = HEIGHT / blockSize;
  const centerX = (cols - 1) / 2;
  const centerY = (rows - 1) / 2;
  const maxRadius = Math.hypot(centerX, centerY);

  const blocks: React.ReactNode[] = [];
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const radial = Math.hypot(col - centerX, row - centerY) / maxRadius;
      const threshold =
        RADIAL_WEIGHT * radial +
        RANDOM_WEIGHT * random(`${seed}:${row}:${col}`);
      const start = threshold * STAGGER_FRAMES;
      const opacity = 1 - interpolate(
        frame,
        [start, start + BLOCK_FADE_FRAMES],
        [0, 1],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      );
      if (opacity <= 0) continue;
      blocks.push(
        <div
          key={`${row}-${col}`}
          style={{
            position: "absolute",
            left: col * blockSize,
            top: row * blockSize,
            width: blockSize,
            height: blockSize,
            backgroundImage: `url("${staticFile(seg.image)}")`,
            backgroundSize: `${WIDTH}px ${HEIGHT}px`,
            backgroundPosition: `-${col * blockSize}px -${row * blockSize}px`,
            opacity,
          }}
        />,
      );
    }
  }
  return <AbsoluteFill>{blocks}</AbsoluteFill>;
};

const SegmentView: React.FC<{
  seg: SegmentInput;
  fps: number;
  input: EpisodeInput;
  prev: SegmentInput | undefined;
}> = ({ seg, fps, input, prev }) => {
  const frame = useCurrentFrame();
  const dur = segmentFrames(seg, fps);
  const stingFrames = Math.round(input.stingFrames ?? 180);
  const slot = slotFrames(seg, fps, stingFrames);
  const audioFrom = FLIP_FRAMES + stingPadFrames(seg, fps, stingFrames);

  const transition = transitionKindFromPrevious(seg, prev);
  const overlay = transition && prev ? (
    <PixelTransitionOverlay
      seg={prev}
      seed={`${prev.id}->${seg.id}`}
      blockSize={transition === "content" ? 40 : 60}
    />
  ) : null;

  const showEndCard =
    seg.endCardAtSec != null && frame >= seg.endCardAtSec * fps;

  const audioVol = (f: number) =>
    interpolate(f, [0, 8, dur - 10, dur], [0.85, 1, 1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const stingAudibleFrames = Math.min(stingFrames, slot);
  const stingVolume = (f: number) =>
    interpolate(
      f,
      [
        0,
        Math.min(STING_FADE_IN, stingAudibleFrames),
        Math.max(
          Math.min(STING_FADE_IN, stingAudibleFrames),
          stingAudibleFrames - STING_FADE_OUT,
        ),
        stingAudibleFrames,
      ],
      [0, 1, 1, 0],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      },
    );

  return (
    <AbsoluteFill style={{ backgroundColor: "#0A1628" }}>
      {seg.image ? (
        <>
          <SlotImage seg={seg} opacity={1} />
          {overlay}
        </>
      ) : (
        <>
          <EndCard input={input} speechEndSec={seg.speechEndSec} />
          {overlay}
        </>
      )}
      <Sequence from={audioFrom} durationInFrames={dur}>
        {seg.audio ? (
          <Audio src={staticFile(seg.audio)} volume={audioVol} />
        ) : null}
      </Sequence>
      {seg.sting && input.stingFile ? (
        <Sequence from={0} durationInFrames={stingAudibleFrames}>
          <Audio src={staticFile(input.stingFile)} volume={stingVolume} />
        </Sequence>
      ) : null}
      {seg.endCardAtSec != null ? (
        showEndCard ? (
          <EndCard input={input} speechEndSec={0} />
        ) : null
      ) : seg.speechEndSec != null ? (
        <EndCard input={input} speechEndSec={seg.speechEndSec} />
      ) : null}
    </AbsoluteFill>
  );
};

export const Episode: React.FC<EpisodeInput> = (input) => {
  const { fps, segments } = input;
  let cursor = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#0A1628" }}>
      {segments.map((seg, i) => {
        const from = cursor;
        const slot = slotFrames(seg, fps, input.stingFrames);
        const prev = segments[i - 1];
        cursor += slot;
        return (
          <Sequence
            key={`${seg.order}-${seg.id}`}
            from={from}
            durationInFrames={slot}
          >
            <SegmentView
              seg={seg}
              fps={fps}
              input={input}
              prev={prev}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
