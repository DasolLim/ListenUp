"use client";

import { useEffect, useRef } from "react";
import { Mesh, Program, Renderer, Triangle, Vec3 } from "ogl";

/**
 * The orb that reacts while someone is speaking.
 *
 * Two deliberate departures from the reference implementation this is based on:
 *
 * 1. **It does not open a microphone.** Loudness arrives through `getLevel`,
 *    read from the stream the transcriber already holds. A second getUserMedia
 *    would capture the same device twice with conflicting constraints — STT
 *    wants echo cancellation and noise suppression, a visualiser wants neither.
 * 2. **The palette is the product's, not the reference's.** The original ships
 *    purple/blue/navy; these are the coral ramp from `.orb` in globals.css, so
 *    the orb reads as the same brand mark that appears elsewhere.
 *
 * It is decorative: `aria-hidden`, because the caption text and the status line
 * already say what is happening. A screen-reader user gains nothing from it and
 * should not have to hear about it.
 */

const vertex = /* glsl */ `
  precision highp float;
  attribute vec2 position;
  attribute vec2 uv;
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position, 0.0, 1.0);
  }
`;

const fragment = /* glsl */ `
  precision highp float;

  uniform float iTime;
  uniform vec3  iResolution;
  uniform float level;      // 0..1 mic amplitude (listening only)
  uniform float brightness; // 0..1 spectral tilt — timbre, not volume
  uniform float breathe;    // 0..1 slow idle pulse, ~5s cycle
  uniform float onset;      // 0..1 decaying accent when speech starts
  uniform float thinking;   // 0..1 tight internal churn, no amplitude
  uniform float talking;    // 0..1 rhythmic pulse while WE speak (TTS)
  uniform float rot;
  varying vec2  vUv;

  // The three stops of .orb in globals.css, exactly — #fbc9a8 / #e8804f /
  // #c9522b. The animated orb and the static logo are meant to be one object, so
  // the palette is copied rather than interpreted.
  //
  // An earlier pass invented a near-black #762814 for the reference image's dark
  // translucent interior. That colour is what read as a black outline: where the
  // inner glow fell off near the edge, the surface fell all the way to it.
  // Nothing here is darker than the logo's darkest stop.
  const vec3 peach = vec3(0.984, 0.788, 0.659);
  const vec3 coral = vec3(0.910, 0.502, 0.310);
  const vec3 ember = vec3(0.788, 0.322, 0.169);

  vec3 hash33(vec3 p3) {
    p3 = fract(p3 * vec3(0.1031, 0.11369, 0.13787));
    p3 += dot(p3, p3.yxz + 19.19);
    return -1.0 + 2.0 * fract(vec3(p3.x + p3.y, p3.x + p3.z, p3.y + p3.z) * p3.zyx);
  }

  float snoise3(vec3 p) {
    const float K1 = 0.333333333;
    const float K2 = 0.166666667;
    vec3 i  = floor(p + (p.x + p.y + p.z) * K1);
    vec3 d0 = p - (i - (i.x + i.y + i.z) * K2);
    vec3 e  = step(vec3(0.0), d0 - d0.yzx);
    vec3 i1 = e * (1.0 - e.zxy);
    vec3 i2 = 1.0 - e.zxy * (1.0 - e);
    vec3 d1 = d0 - (i1 - K2);
    vec3 d2 = d0 - (i2 - K1);
    vec3 d3 = d0 - 0.5;
    vec4 h  = max(0.6 - vec4(dot(d0,d0), dot(d1,d1), dot(d2,d2), dot(d3,d3)), 0.0);
    vec4 n  = h * h * h * h * vec4(dot(d0, hash33(i)), dot(d1, hash33(i + i1)),
                                   dot(d2, hash33(i + i2)), dot(d3, hash33(i + 1.0)));
    return dot(vec4(31.316), n);
  }

  void main() {
    vec2 fragCoord = vUv * iResolution.xy;
    vec2 center = iResolution.xy * 0.5;
    float size  = min(iResolution.x, iResolution.y);
    vec2 uv = (fragCoord - center) / size * 2.2;

    float ang = atan(uv.y, uv.x);
    float len = length(uv);

    // Amplitude and churn are separate drivers, which is what keeps the states
    // distinguishable: thinking churns without swelling, a loud voice swells.
    float amp   = clamp(level + onset * 0.5, 0.0, 1.0);
    // Roughly half the previous rates. The states still separate clearly, but
    // the surface drifts instead of boiling — this sits next to live captions
    // someone is reading, so restless motion competes with the text.
    // Tuned by measuring shape swing against rate of change. Amplitude carries
    // the expressiveness (swing 0.17 -> 0.31, larger than the version that felt
    // frantic), so the turbulence rate can come *down* rather than up: rate is
    // roughly amplitude x frequency, and it is the frequency that reads as
    // restless. Net result is bigger, slower, more fluid motion.
    float churn = 0.11 + amp * 0.50 + thinking * 0.8 + talking * 0.22;

    // Silhouette. Sampling noise on the unit circle keeps it seamless at the
    // wrap, and two octaves give the reference's look: a few broad lobes with
    // finer creases on top, rather than a fuzzy or perfectly round edge.
    // rot drifts the sample angle so the lobes travel slowly around the rim
    // instead of pulsing in place — the turbulence drift that keeps an idle orb
    // from looking like a looping animation.
    float drift = ang + rot;
    float lobes  = snoise3(vec3(cos(drift) * 1.15, sin(drift) * 1.15, iTime * churn));
    float creases= snoise3(vec3(cos(drift) * 3.30, sin(drift) * 3.30, iTime * churn * 1.4));

    // The whole body swells, not just its edge. This is the single biggest
    // contributor to feeling alive: a voice should visibly inflate the orb,
    // where before only the silhouette rippled and the size held constant.
    float rest = 0.68 + breathe * 0.075 + amp * 0.115 + talking * 0.055;
    // Louder syllables push the edge out further and sharpen the creases.
    // Weighted toward the broad lobes and away from the fine creases: big slow
    // morphing reads as fluid, while high-frequency detail reads as noise and is
    // what made this look busy at speed.
    float radius = rest
                 + lobes   * (0.075 + amp * 0.145)
                 + creases * (0.005 + amp * 0.010 + thinking * 0.004);

    // Feather the edge in PIXELS, not in uv units. This orb renders anywhere
    // from 64 to 176 CSS px at 1x-2x DPR, and the previous fixed 0.030 uv
    // feather worked out to 0.87px on the small orb (a visibly stair-stepped
    // edge) and 4.8px on the large one. One constant cannot serve both.
    //
    // MSAA does not help here: the silhouette is computed in this shader on a
    // full-screen triangle, so the only geometry edge the GPU antialiases is
    // that triangle, off-screen. The edge quality is entirely this smoothstep.
    float px = 2.2 / min(iResolution.x, iResolution.y);
    float feather = max(px * 1.6, 0.014 + amp * 0.008);
    float inside = smoothstep(radius + feather, radius - feather, len);
    if (inside <= 0.001 && len > radius + 0.55) discard;

    // One gradient, mirroring radial-gradient(circle at 35% 30%): the
    // highlight sits up and to the left, coral at the midpoint, ember at the
    // rim. No separate rim light and no dark core — every band those added was
    // another edge that could read as a line across the surface.
    vec2 lightAt = vec2(-0.30, 0.40);
    float g = clamp(distance(uv, lightAt) / 1.45, 0.0, 1.0);
    vec3 col = mix(peach, coral, smoothstep(0.0, 0.55, g));
    col = mix(col, ember, smoothstep(0.55, 1.0, g));

    // Speaking lifts it toward the highlight rather than adding a new colour, so
    // it brightens without ever leaving the ramp.
    col = mix(col, peach, clamp(amp * 0.30 + talking * 0.12 + brightness * 0.08, 0.0, 1.0));

    // No outer halo. It was a wide soft bloom reaching well past the silhouette,
    // and on a light glass card it read as a grey wash filling the canvas rather
    // than as light. The orb now ends where its edge ends; the pixel-width
    // feather below alone keeps that edge from looking cut out.
    float alpha = inside * 0.96;
    col = clamp(col, 0.0, 1.0);
    gl_FragColor = vec4(col * alpha, alpha);
  }
`;

export default function VoiceOrb({
  getSignal,
  state = "idle",
  className = "",
}: {
  /** Loudness + timbre, sampled per frame — never through React state. */
  getSignal: () => { level: number; brightness: number };
  /**
   * What the orb is saying. Distinct forms rather than one intensity dial:
   *
   *   idle      slow scale breathing, ~5s cycle — live and waiting
   *   thinking  fast tight churn, no swelling — work with no audio behind it
   *   listening mic amplitude drives displacement and turbulence
   *   speaking  a rhythmic pulse of our own, so "it is talking" never looks
   *             like "you are talking"
   *
   * The distinction matters most to the person this product is for — someone
   * who cannot hear whether their microphone is working.
   */
  state?: "idle" | "thinking" | "listening" | "speaking";
  className?: string;
}) {
  const mount = useRef<HTMLDivElement>(null);
  // Held in a ref so the render loop always calls the latest reader without the
  // effect re-running (and tearing down the WebGL context) on every render.
  const signalRef = useRef(getSignal);
  useEffect(() => {
    signalRef.current = getSignal;
  }, [getSignal]);
  // Read inside the frame loop so a state change doesn't tear down the context.
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const container = mount.current;
    if (!container) return;

    // Reduced motion is a hard requirement (§7): fall back to the static CSS
    // orb rather than a slower animation. The caption text carries the meaning.
    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) return;

    let renderer: Renderer;
    try {
      renderer = new Renderer({ alpha: true, premultipliedAlpha: false, antialias: true });
    } catch {
      return; // no WebGL — the CSS orb underneath stays visible
    }

    const gl = renderer.gl;
    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    container.appendChild(gl.canvas);

    const program = new Program(gl, {
      vertex,
      fragment,
      uniforms: {
        iTime: { value: 0 },
        iResolution: { value: new Vec3(1, 1, 1) },
        level: { value: 0 },
        brightness: { value: 0 },
        breathe: { value: 0 },
        onset: { value: 0 },
        thinking: { value: 0 },
        talking: { value: 0 },
        rot: { value: 0 },
      },
    });
    const mesh = new Mesh(gl, { geometry: new Triangle(gl), program });

    const resize = () => {
      // Cap DPR at 2: a 3x retina canvas triples fragment work for no visible
      // gain, and this runs alongside live transcription and speaker matching.
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const { clientWidth: w, clientHeight: h } = container;
      if (!w || !h) return;
      renderer.setSize(w * dpr, h * dpr);
      gl.canvas.style.width = `${w}px`;
      gl.canvas.style.height = `${h}px`;
      program.uniforms.iResolution.value.set(
        gl.canvas.width,
        gl.canvas.height,
        gl.canvas.width / gl.canvas.height
      );
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    let frame = 0;
    let last = 0;
    let rotation = 0;
    let smoothed = 0;
    let smoothBright = 0;
    let onset = 0;
    let thinking = 0;
    let speaking = 0;
    let talking = 0;

    const draw = (time: number) => {
      frame = requestAnimationFrame(draw);
      const dt = last ? Math.min((time - last) * 0.001, 0.1) : 0;
      last = time;
      const seconds = time * 0.001;
      const mode = stateRef.current;

      // Ease toward the measured level: raw RMS is spiky enough to make the orb
      // stutter on every syllable. Rising fast and falling slowly matches how a
      // voice actually sounds — quick onset, gentle decay.
      const signal = mode === "listening" ? signalRef.current() : { level: 0, brightness: 0 };
      const previous = smoothed;
      // Asymmetric on purpose, and that asymmetry is most of what makes it feel
      // alive: it rises with the voice but glides back, so a sentence leaves a
      // slow swell rather than a flicker. Still well below the 0.35 that had it
      // snapping to every syllable edge.
      const ease = signal.level > smoothed ? 0.22 : 0.045;
      smoothed += (signal.level - smoothed) * ease;
      smoothBright += (signal.brightness - smoothBright) * 0.12;

      // Fire an accent when speech *starts* — the transition from silence is the
      // moment worth punctuating, and a decaying pulse reads as an event where a
      // rising level alone just reads as "more".
      // Scale the accent to the voice that triggered it. A flat +0.5 made a
      // quiet "hello" bloom as hard as a shout, which inverted the whole point
      // of an amplitude-driven orb.
      if (previous < 0.12 && smoothed >= 0.12) onset = Math.min(1, smoothed * 2.2);
      onset = Math.max(0, onset - dt * 1.1); // twice as long, half as abrupt

      // Blend states rather than switching, so a change is a transition.
      thinking += ((mode === "thinking" ? 1 : 0) - thinking) * 0.12;

      // Speaking gets its own rhythm — a ~2.6 Hz pulse driven by nothing but the
      // clock. It must not borrow the mic, or the orb would react to the room
      // while the app is the one talking.
      //
      // Presence and rhythm are tracked separately on purpose: `speaking` is
      // "are we in this state", `pulse` is the beat. Deriving both from one
      // oscillating value let the orb resume breathing at every trough of the
      // pulse, so the two motions fought each other.
      speaking += ((mode === "speaking" ? 1 : 0) - speaking) * 0.12;
      const pulse = Math.sin(seconds * 1.5) * 0.5 + 0.5; // ~4s, a calm cadence
      talking = speaking * pulse;

      // Breathing is the resting signal: ~5.7s cycle, fading out as a voice or a
      // spoken reply takes over so the states never read as the same thing.
      const busy = Math.min(1, smoothed * 2.5 + thinking + speaking);
      const breathing = (Math.sin(seconds * 0.95) * 0.5 + 0.5) * (1 - busy); // ~6.6s

      // A slow drift rather than a spin. At the previous rate a loud voice spun
      // the silhouette fast enough to read as agitation rather than response.
      rotation += dt * (0.05 + smoothed * 0.42 + thinking * 0.34 + talking * 0.12);
      program.uniforms.iTime.value = seconds;
      program.uniforms.level.value = smoothed;
      program.uniforms.brightness.value = smoothBright;
      program.uniforms.breathe.value = breathing;
      program.uniforms.onset.value = onset;
      program.uniforms.thinking.value = thinking;
      program.uniforms.talking.value = talking;
      program.uniforms.rot.value = rotation;

      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      renderer.render({ scene: mesh });
    };
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      if (gl.canvas.parentNode === container) container.removeChild(gl.canvas);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    };
  }, []);

  return (
    <div aria-hidden="true" className={`group relative isolate ${className}`}>
      {/* The static brand orb sits underneath, so reduced-motion users, devices
          without WebGL, and the moment before the canvas mounts all still see
          an orb rather than a hole in the layout. */}
      <span
        // Hidden precisely when a canvas exists, expressed in CSS rather than
        // React state: the fallback is not a backdrop, and leaving its hard edge
        // and drop shadow behind a live shader rings the orb and reads as double.
        className="orb absolute inset-0 block h-full w-full transition-opacity duration-300 group-has-[canvas]:opacity-0"
      />
      <div ref={mount} className="absolute inset-0" />
    </div>
  );
}
