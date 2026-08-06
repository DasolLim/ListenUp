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
  uniform float level;      // 0..1 speaking loudness
  uniform float rot;
  varying vec2  vUv;

  // The coral ramp from globals.css .orb — peach highlight, coral body, deep
  // coral core — so this is recognisably the same orb as the static brand mark.
  const vec3 highlight = vec3(0.984, 0.788, 0.659);
  const vec3 body      = vec3(0.910, 0.502, 0.310);
  const vec3 core      = vec3(0.788, 0.322, 0.169);

  const float innerRadius = 0.6;
  const float noiseScale  = 0.65;

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

  vec4 extractAlpha(vec3 c) {
    float a = max(max(c.r, c.g), c.b);
    return vec4(c / (a + 1e-5), a);
  }

  float light1(float intensity, float attenuation, float dist) {
    return intensity / (1.0 + dist * attenuation);
  }
  float light2(float intensity, float attenuation, float dist) {
    return intensity / (1.0 + dist * dist * attenuation);
  }

  vec4 draw(vec2 uv) {
    float ang    = atan(uv.y, uv.x);
    float len    = length(uv);
    float invLen = len > 0.0 ? 1.0 / len : 0.0;

    // Louder speech ripples the surface harder and quickens the churn, so the
    // motion reads as "how loudly am I speaking" rather than a fixed idle.
    float churn = 0.35 + level * 1.4;
    float n0 = snoise3(vec3(uv * noiseScale, iTime * churn)) * 0.5 + 0.5;
    float wobble = 0.4 + level * 0.35;
    float r0 = mix(mix(innerRadius, 1.0, wobble), mix(innerRadius, 1.0, 0.6), n0);

    float d0 = distance(uv, (r0 * invLen) * uv);
    float v0 = light1(1.0, 10.0, d0) * smoothstep(r0 * 1.05, r0, len);
    float cl = cos(ang + iTime * 2.0) * 0.5 + 0.5;

    float a   = iTime * -1.0;
    vec2  pos = vec2(cos(a), sin(a)) * r0;
    float d   = distance(uv, pos);
    float v1  = light2(1.5, 5.0, d) * light1(1.0, 50.0, d0);

    float v2 = smoothstep(1.0, mix(innerRadius, 1.0, n0 * 0.5), len);
    float v3 = smoothstep(innerRadius, mix(innerRadius, 1.0, 0.5), len);

    vec3 col = mix(body, highlight, cl);
    col = mix(core, col, v0);
    col = (col + v1 * (0.6 + level)) * v2 * v3;
    return extractAlpha(clamp(col, 0.0, 1.0));
  }

  void main() {
    vec2 fragCoord = vUv * iResolution.xy;
    vec2 center = iResolution.xy * 0.5;
    float size  = min(iResolution.x, iResolution.y);
    vec2 uv = (fragCoord - center) / size * 2.0;

    float s = sin(rot), c = cos(rot);
    uv = vec2(c * uv.x - s * uv.y, s * uv.x + c * uv.y);

    // Surface displacement scales with loudness — silence leaves a calm sphere.
    float push = level * 0.16;
    uv.x += push * sin(uv.y * 10.0 + iTime);
    uv.y += push * sin(uv.x * 10.0 + iTime);

    vec4 col = draw(uv);
    gl_FragColor = vec4(col.rgb * col.a, col.a);
  }
`;

export default function VoiceOrb({
  getLevel,
  active,
  className = "",
}: {
  /** Reads current loudness 0–1. Sampled per frame, never through React state. */
  getLevel: () => number;
  /** Animate only while captions are running; idle sessions cost nothing. */
  active: boolean;
  className?: string;
}) {
  const mount = useRef<HTMLDivElement>(null);
  // Held in a ref so the render loop always calls the latest reader without the
  // effect re-running (and tearing down the WebGL context) on every render.
  const levelRef = useRef(getLevel);
  useEffect(() => {
    levelRef.current = getLevel;
  }, [getLevel]);

  useEffect(() => {
    const container = mount.current;
    if (!container) return;

    // Reduced motion is a hard requirement (§7): fall back to the static CSS
    // orb rather than a slower animation. The caption text carries the meaning.
    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion || !active) return;

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

    const draw = (time: number) => {
      frame = requestAnimationFrame(draw);
      const dt = last ? (time - last) * 0.001 : 0;
      last = time;

      // Ease toward the measured level: raw RMS is spiky enough to make the orb
      // stutter on every syllable. Rising fast and falling slowly matches how a
      // voice actually sounds — quick onset, gentle decay.
      const target = levelRef.current();
      const ease = target > smoothed ? 0.35 : 0.08;
      smoothed += (target - smoothed) * ease;

      rotation += dt * (0.25 + smoothed * 1.6);
      program.uniforms.iTime.value = time * 0.001;
      program.uniforms.level.value = smoothed;
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
  }, [active]);

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
