"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useGateway } from "@/lib/gateway-context";
import type { GatewayEnvelope } from "@/lib/websocket";
import type { DataChangeEvent } from "@/lib/types";

const ACTIVE_ACTIONS = new Set(["discovering", "analyzing", "evaluating", "drafting", "started", "created"]);
const DONE_ACTIONS = new Set(["completed", "failed"]);
const SHOW_AFTER_MS = 5_000;
const DISPLAY_SIZE = 40;
const RENDER_SIZE = 256; // render at high res, display small

const VERT = `
  varying vec3 vNormal;
  varying vec3 vViewDir;
  varying vec3 vWorldNormal;
  varying vec3 vWorldPos;
  uniform float uTime;

  void main() {
    float breathe = sin(uTime * 0.4) * 0.02;
    vec3 pos = position * (1.0 + breathe);
    vec4 worldPos = modelMatrix * vec4(pos, 1.0);
    vWorldPos = worldPos.xyz;
    vWorldNormal = normalize(mat3(modelMatrix) * normal);
    vNormal = normalize(normalMatrix * normal);
    vViewDir = normalize(cameraPosition - worldPos.xyz);
    gl_Position = projectionMatrix * viewMatrix * worldPos;
  }
`;

const FRAG = `
  precision highp float;
  varying vec3 vNormal;
  varying vec3 vViewDir;
  varying vec3 vWorldNormal;
  varying vec3 vWorldPos;
  uniform float uTime;
  uniform vec3 uLightDir;

  float hash3D(vec3 p) {
    return fract(sin(dot(p, vec3(12.9898, 78.233, 45.5432))) * 43758.5453);
  }

  float valNoise(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash3D(i);
    float b = hash3D(i + vec3(1,0,0));
    float c = hash3D(i + vec3(0,1,0));
    float d = hash3D(i + vec3(1,1,0));
    float e = hash3D(i + vec3(0,0,1));
    float f2 = hash3D(i + vec3(1,0,1));
    float g = hash3D(i + vec3(0,1,1));
    float h = hash3D(i + vec3(1,1,1));
    return mix(
      mix(mix(a,b,f.x), mix(c,d,f.x), f.y),
      mix(mix(e,f2,f.x), mix(g,h,f.x), f.y),
      f.z
    );
  }

  void main() {
    vec3 N = normalize(vWorldNormal);
    vec3 V = normalize(vViewDir);
    vec3 R = reflect(-V, N);
    float fresnel = pow(1.0 - max(dot(N, V), 0.0), 3.0);
    float n1 = valNoise(R * 2.0 + uTime);
    float n2 = valNoise(R * 2.0 - uTime);
    float n3 = valNoise(R * 3.0 + uTime * 0.5);
    vec3 base = vec3(0.35, 0.42, 0.58);
    vec3 brandBlue = vec3(0.145, 0.388, 0.922);
    vec3 accentBlue = vec3(0.231, 0.510, 0.965);
    vec3 lightBlue = vec3(0.537, 0.706, 1.0);
    vec3 swirl = vec3(0.0);
    swirl += brandBlue * smoothstep(0.3, 0.55, n1) * 0.7;
    swirl += accentBlue * smoothstep(0.3, 0.55, n2) * 0.7;
    swirl += lightBlue * smoothstep(0.35, 0.6, n3) * 0.5;
    vec3 color = base + swirl;
    float diff = max(dot(N, uLightDir), 0.0) * 0.15;
    color += vec3(1.0) * diff;
    float spec = pow(max(dot(R, uLightDir), 0.0), 120.0);
    color += vec3(1.0) * spec * 0.9;
    vec3 light2 = normalize(vec3(-0.4, 0.3, 0.8));
    float spec2 = pow(max(dot(R, light2), 0.0), 60.0);
    color += vec3(0.95, 0.97, 1.0) * spec2 * 0.5;
    float clearcoat = pow(max(dot(R, uLightDir), 0.0), 8.0);
    color += vec3(1.0) * clearcoat * 0.08;
    vec3 rimColor = mix(accentBlue, vec3(1.0), 0.5);
    color = mix(color, rimColor, fresnel * 0.5);
    vec3 envUp = vec3(0.85, 0.92, 1.0);
    vec3 envDown = vec3(1.0, 1.0, 1.0);
    vec3 envColor = mix(envDown, envUp, R.y * 0.5 + 0.5);
    color = mix(color, envColor, fresnel * 0.3);
    gl_FragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
  }
`;

/**
 * Animated 3D droplet in the center of the nav bar. Only visible when
 * a background task has been running for 5+ seconds. Links to /system.
 */
export function ActivityIndicator() {
  const [active, setActive] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<{ dispose: () => void } | null>(null);
  const rafRef = useRef<number | null>(null);
  const { addListener, removeListener } = useGateway();

  const showTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeTasksRef = useRef(0); // count of in-flight tasks

  // Check for running tasks on mount (page refresh while task in progress)
  useEffect(() => {
    fetch("/api/tasks?status=running")
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.tasks?.length > 0) {
          activeTasksRef.current = data.tasks.length;
          setActive(true);
        }
      })
      .catch(() => {}); // silent — if API not ready yet, events will catch up
  }, []);

  // Event detection
  useEffect(() => {
    const handler = (envelope: GatewayEnvelope) => {
      if (envelope.type !== "event") return;
      const payload = envelope.payload as Record<string, unknown>;
      if (payload.type !== "data_change") return;
      const data = payload.data as DataChangeEvent | undefined;
      if (!data) return;

      // Only track task lifecycle — pipeline stage events fire multiple times
      // per task without matching completion signals
      const isStart = data.entity === "task" && ACTIVE_ACTIONS.has(data.action);
      const isDone = data.entity === "task" && DONE_ACTIONS.has(data.action);

      if (isStart) {
        activeTasksRef.current += 1;
        // Start debounce-in timer on first activity
        if (!showTimerRef.current) {
          showTimerRef.current = setTimeout(() => {
            if (activeTasksRef.current > 0) setActive(true);
            showTimerRef.current = null;
          }, SHOW_AFTER_MS);
        }
      } else if (isDone) {
        activeTasksRef.current = Math.max(0, activeTasksRef.current - 1);
        if (activeTasksRef.current === 0) {
          if (showTimerRef.current) { clearTimeout(showTimerRef.current); showTimerRef.current = null; }
          setActive(false);
        }
      }
    };
    addListener("activity-indicator", handler);
    return () => {
      removeListener("activity-indicator");
      if (showTimerRef.current) clearTimeout(showTimerRef.current);
    };
  }, [addListener, removeListener]);

  // Three.js setup — only mount when active
  useEffect(() => {
    if (!active || !canvasRef.current) return;

    let disposed = false;

    import("three").then((THREE) => {
      if (disposed || !canvasRef.current) return;

      const canvas = canvasRef.current;
      const scene = new THREE.Scene();
      scene.background = null; // transparent

      const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
      camera.position.z = 3.2;

      const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
      renderer.setPixelRatio(1); // we handle resolution ourselves
      renderer.setSize(RENDER_SIZE, RENDER_SIZE, false);
      canvas.width = RENDER_SIZE;
      canvas.height = RENDER_SIZE;
      renderer.setClearColor(0x000000, 0);
      rendererRef.current = renderer;

      const geometry = new THREE.IcosahedronGeometry(1, 128);
      const uniforms = {
        uTime: { value: 0 },
        uLightDir: { value: new THREE.Vector3(0.5, 0.8, 0.5).normalize() },
      };
      const material = new THREE.ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: FRAG });
      const sphere = new THREE.Mesh(geometry, material);
      scene.add(sphere);

      const clock = new THREE.Clock();
      function animate() {
        if (disposed) return;
        rafRef.current = requestAnimationFrame(animate);
        const t = clock.getElapsedTime();
        uniforms.uTime.value = t * 1.0;
        sphere.rotation.y = t * 0.1;
        sphere.rotation.x = t * 0.075;
        renderer.render(scene, camera);
      }
      animate();
    });

    return () => {
      disposed = true;
      if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
      if (rendererRef.current) { rendererRef.current.dispose(); rendererRef.current = null; }
    };
  }, [active]);

  return (
    <Link
      href="/system"
      aria-label="System activity"
      title="Pipeline running — click to view"
      className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 transition-opacity duration-1000 ${active ? "opacity-100 ease-in" : "pointer-events-none opacity-0 ease-out"}`}
    >
      <canvas
        ref={canvasRef}
        width={RENDER_SIZE}
        height={RENDER_SIZE}
        className="block rounded-full"
        style={{ width: DISPLAY_SIZE, height: DISPLAY_SIZE }}
      />
    </Link>
  );
}
