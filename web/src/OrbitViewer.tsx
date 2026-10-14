import { Button, Flex, Select, Text } from '@radix-ui/themes';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DataPoint, Quaternion, Vector } from 'simulation';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

// Matches Plotly's default trace colors, so bodies look the same as in the plots.
const COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728'];
const SPEEDS = [0.25, 0.5, 1, 2, 4];
// At 1x, the whole simulation plays in this many seconds.
const BASE_PLAYBACK_SECONDS = 20;

// The states of one agent in time order, starting with its initial state.
interface Track {
  agentId: string;
  times: number[];
  positions: THREE.Vector3[];
  attitudes: THREE.Quaternion[];
  model?: NonNullable<DataPoint[2][string]['model']>;
}

const toVector3 = (v: Vector) => new THREE.Vector3(v.x, v.y, v.z);
const toQuaternion = (q: Quaternion | undefined) => (q ? new THREE.Quaternion(q.x, q.y, q.z, q.w) : new THREE.Quaternion());

function buildTracks(data: DataPoint[]): Track[] {
  const initial = data[0][2];
  return Object.entries(initial).map(([agentId, state]) => {
    const states = [state, ...data.slice(1).flatMap(([, , frame]) => (frame[agentId] ? [frame[agentId]] : []))];
    return {
      agentId,
      times: states.map((s) => s.time),
      positions: states.map((s) => toVector3(s.position)),
      attitudes: states.map((s) => toQuaternion(s.attitude)),
      model: state.model,
    };
  });
}

// Position and attitude of a track at time `t`, interpolated between its two surrounding states.
function sample(track: Track, t: number, position: THREE.Vector3, attitude: THREE.Quaternion) {
  const { times } = track;
  let hi = times.findIndex((time) => time >= t);
  if (hi === -1) hi = times.length - 1;
  const lo = Math.max(hi - 1, 0);
  const span = times[hi] - times[lo];
  const f = span > 0 ? Math.min(Math.max((t - times[lo]) / span, 0), 1) : 0;
  position.lerpVectors(track.positions[lo], track.positions[hi], f);
  attitude.slerpQuaternions(track.attitudes[lo], track.attitudes[hi], f);
}

// Geometry of a model's mesh (stored relative to its center of mass), scaled to simulation units.
// Models uploaded before meshes were stored fall back to their bounding box.
async function loadModelGeometry(model: NonNullable<Track['model']>): Promise<THREE.BufferGeometry> {
  const response = await fetch(`http://localhost:8000/models/${model.id}/mesh`);
  if (!response.ok) {
    return new THREE.BoxGeometry(model.dimensions.x, model.dimensions.y, model.dimensions.z);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(await response.arrayBuffer()), 3));
  geometry.scale(model.scale, model.scale, model.scale);
  geometry.computeVertexNormals();
  return geometry;
}

interface OrbitViewerProps {
  data: DataPoint[];
}

const OrbitViewer: React.FC<OrbitViewerProps> = ({ data }) => {
  const tracks = useMemo(() => buildTracks(data), [data]);
  const startTime = Math.max(...tracks.map((track) => track.times[0]));
  // Play until the first agent runs out of states, so every agent is defined throughout.
  const endTime = Math.min(...tracks.map((track) => track.times[track.times.length - 1]));

  const containerRef = useRef<HTMLDivElement>(null);
  const followRef = useRef<string>('system');
  const snapRef = useRef(false); // move the camera close to the followed body on the next render
  const timeRef = useRef(startTime);
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  const renderRef = useRef<() => void>(() => {});

  const [time, setTime] = useState(startTime);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [follow, setFollow] = useState('system');

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let disposed = false;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#ffffff');
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.2);
    sun.position.set(1, 1, 2);
    scene.add(sun);

    // Size the scene from the extent of all trajectories.
    const bounds = new THREE.Box3();
    tracks.forEach((track) => track.positions.forEach((p) => bounds.expandByPoint(p)));
    const extent = Math.max(bounds.getSize(new THREE.Vector3()).length(), 1);
    const center = bounds.getCenter(new THREE.Vector3());

    const camera = new THREE.PerspectiveCamera(45, 1, extent / 1000, extent * 20);
    camera.up.set(0, 0, 1); // the simulation's z axis points up
    camera.position.copy(center).add(new THREE.Vector3(0.6, -0.9, 0.7).multiplyScalar(extent));

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.domElement.setAttribute('role', 'img');
    renderer.domElement.setAttribute('aria-label', 'Animated 3D view of the simulated bodies and their trajectories');
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.update();

    scene.add(new THREE.GridHelper(extent, 20, 0xcccccc, 0xeeeeee).rotateX(Math.PI / 2).translateY(center.z));

    const bodies = tracks.map((track, i) => {
      const color = COLORS[i % COLORS.length];
      const line = new THREE.BufferGeometry().setFromPoints(track.positions);
      scene.add(new THREE.Line(line, new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.5 })));

      const body = new THREE.Group();
      if (track.model) {
        const model = track.model;
        loadModelGeometry(model).then((geometry) => {
          if (disposed) return geometry.dispose();
          body.add(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color, metalness: 0.2, roughness: 0.6 })));
          renderRef.current();
        });
        // Body axes (x red, y green, z blue) make the rotation easy to read.
        body.add(new THREE.AxesHelper(model.size * 0.75));
      } else {
        body.add(new THREE.Mesh(new THREE.SphereGeometry(extent / 150, 24, 16), new THREE.MeshStandardMaterial({ color })));
      }
      scene.add(body);
      return body;
    });

    const position = new THREE.Vector3();
    const attitude = new THREE.Quaternion();
    const render = () => {
      tracks.forEach((track, i) => {
        sample(track, timeRef.current, position, attitude);
        bodies[i].position.copy(position);
        bodies[i].quaternion.copy(attitude);
      });
      // Following a body: move the camera with it, keeping the user's viewing angle and distance.
      const followed = tracks.findIndex((track) => track.agentId === followRef.current);
      if (followed >= 0) {
        const target = bodies[followed].position;
        if (snapRef.current) {
          // Start close enough to see the body itself: a couple of body lengths away.
          const size = tracks[followed].model?.size ?? extent / 75;
          const direction = camera.position.clone().sub(controls.target).normalize();
          camera.position.copy(target).addScaledVector(direction, size * 2.5);
          snapRef.current = false;
        } else {
          camera.position.add(target.clone().sub(controls.target));
        }
        controls.target.copy(target);
      } else if (snapRef.current) {
        // Back to the whole system.
        camera.position.copy(center).add(new THREE.Vector3(0.6, -0.9, 0.7).multiplyScalar(extent));
        controls.target.copy(center);
        snapRef.current = false;
      }
      controls.update();
      renderer.render(scene, camera);
    };
    renderRef.current = render;

    const resize = () => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    controls.addEventListener('change', () => renderer.render(scene, camera));

    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const elapsed = (now - last) / 1000;
      last = now;
      if (playingRef.current) {
        const rate = ((endTime - startTime) / BASE_PLAYBACK_SECONDS) * speedRef.current;
        timeRef.current = Math.min(timeRef.current + elapsed * rate, endTime);
        if (timeRef.current >= endTime) {
          playingRef.current = false;
          setPlaying(false);
        }
        setTime(timeRef.current);
        render();
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
          object.geometry.dispose();
          (Array.isArray(object.material) ? object.material : [object.material]).forEach((m) => m.dispose());
        }
      });
      renderer.dispose();
      container.removeChild(renderer.domElement);
    };
  }, [tracks, startTime, endTime]);

  const togglePlaying = useCallback(() => {
    if (!playingRef.current && timeRef.current >= endTime) {
      timeRef.current = startTime; // replay from the start
    }
    playingRef.current = !playingRef.current;
    setPlaying(playingRef.current);
  }, [startTime, endTime]);

  const scrub = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    timeRef.current = parseFloat(e.target.value);
    setTime(timeRef.current);
    renderRef.current();
  }, []);

  const changeSpeed = useCallback((value: string) => {
    speedRef.current = parseFloat(value);
    setSpeed(speedRef.current);
  }, []);

  const changeFollow = useCallback((value: string) => {
    followRef.current = value;
    snapRef.current = true;
    setFollow(value);
    renderRef.current();
  }, []);

  return (
    <Flex direction="column" gap="2" style={{ width: '90%' }}>
      <div ref={containerRef} style={{ width: '100%', height: '500px', borderRadius: 4, overflow: 'hidden' }} />
      <Flex gap="3" align="center" wrap="wrap">
        <Button type="button" onClick={togglePlaying} aria-pressed={playing}>
          {playing ? 'Pause' : 'Play'}
        </Button>
        <input
          type="range"
          aria-label="Simulation time"
          min={startTime}
          max={endTime}
          step={(endTime - startTime) / 1000}
          value={time}
          onChange={scrub}
          style={{ flex: 1, minWidth: 200 }}
        />
        <Text size="2" style={{ fontVariantNumeric: 'tabular-nums', minWidth: 110 }}>
          t = {time.toFixed(1)} / {endTime.toFixed(0)}
        </Text>
        <Flex gap="1" align="center">
          <Text size="2">Speed</Text>
          <Select.Root value={String(speed)} onValueChange={changeSpeed}>
            <Select.Trigger aria-label="Playback speed" />
            <Select.Content>
              {SPEEDS.map((s) => (
                <Select.Item key={s} value={String(s)}>
                  {s}×
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        </Flex>
        <Flex gap="1" align="center">
          <Text size="2">Camera</Text>
          <Select.Root value={follow} onValueChange={changeFollow}>
            <Select.Trigger aria-label="Camera" />
            <Select.Content>
              <Select.Item value="system">Free</Select.Item>
              {tracks.map((track) => (
                <Select.Item key={track.agentId} value={track.agentId}>
                  Follow {track.agentId}
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        </Flex>
      </Flex>
      <Text size="1" color="gray">
        Drag to orbit, scroll to zoom. CAD models are drawn at their simulated size and orientation with their body axes
        (x red, y green, z blue); point masses are drawn as spheres.
      </Text>
    </Flex>
  );
};

export default OrbitViewer;
