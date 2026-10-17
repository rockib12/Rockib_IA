import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

/**
 * ThreeCanvas — Composant de rendu 3D temps réel avec Three.js
 * Visualise l'univers multi-agents, les miniatures 3D de pods, les lasers
 * de parentage, les particules de spawn et la caméra orbitale interactive.
 *
 * Phase 1 rewrite:
 *  - Fibonacci spiral layout (prevents torus stacking)
 *  - Canvas-text sprite labels floating above each pod
 *  - Richer role-based colours & breathing animation
 *  - Improved fog, starfield, and depth-of-field feel
 */

// ─── Helpers ─────────────────────────────────────────────────────────

/** Map a role string to a primary neon colour. */
function roleToColor(agent) {
  const role = (agent.role || '').toLowerCase();
  const isOrchestrator = !agent.parent_agent_id || role.includes('orchestrator');
  if (agent.current_status === 'RUNNING') return '#10B981'; // emerald
  if (isOrchestrator) return '#00F0FF';                      // cyan
  if (role.includes('security') || role.includes('sentinel')) return '#F59E0B'; // amber
  if (role.includes('scout')) return '#38BDF8';              // sky-blue
  if (role.includes('cognitive') || role.includes('analyst')) return '#EC4899'; // pink
  return '#A855F7';                                          // purple default
}

/** Golden-angle Fibonacci spiral — gives evenly-spaced points on a disc. */
function fibonacciDiscPosition(index, total, baseRadius = 6, spacing = 6.5) {
  if (total <= 1) return new THREE.Vector3(0, 0, 0);
  const goldenAngle = Math.PI * (3 - Math.sqrt(5)); // ~137.5°
  const r = baseRadius + spacing * Math.sqrt(index);
  const theta = index * goldenAngle;
  return new THREE.Vector3(Math.cos(theta) * r, 0, Math.sin(theta) * r);
}

/** Create a floating text sprite using an off-screen canvas. */
function createLabelSprite(text, color = '#FFFFFF') {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const fontSize = 42;
  const padding = 24;

  ctx.font = `700 ${fontSize}px 'Outfit', 'Inter', sans-serif`;
  const metrics = ctx.measureText(text);
  const textWidth = metrics.width;

  canvas.width = textWidth + padding * 2;
  canvas.height = fontSize + padding * 2;

  // Background pill
  ctx.fillStyle = 'rgba(5, 7, 14, 0.78)';
  const rr = canvas.height / 2;
  ctx.beginPath();
  ctx.moveTo(rr, 0);
  ctx.lineTo(canvas.width - rr, 0);
  ctx.arc(canvas.width - rr, rr, rr, -Math.PI / 2, Math.PI / 2);
  ctx.lineTo(rr, canvas.height);
  ctx.arc(rr, rr, rr, Math.PI / 2, -Math.PI / 2);
  ctx.closePath();
  ctx.fill();

  // Neon border
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.shadowColor = color;
  ctx.shadowBlur = 14;
  ctx.stroke();

  // Text
  ctx.font = `700 ${fontSize}px 'Outfit', 'Inter', sans-serif`;
  ctx.fillStyle = '#FFFFFF';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.shadowColor = color;
  ctx.shadowBlur = 10;
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);

  // Sprite from canvas
  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  const mat = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
  });
  const sprite = new THREE.Sprite(mat);
  const aspect = canvas.width / canvas.height;
  const spriteHeight = 1.6;
  sprite.scale.set(spriteHeight * aspect, spriteHeight, 1);

  return sprite;
}

// ─── Component ───────────────────────────────────────────────────────

export default function ThreeCanvas({
  agents = [],
  selectedAgentId,
  onSelectAgent,
  isSplitView,
  spawnEvent, // { agentId, parentId, timestamp }
}) {
  const mountRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const rendererRef = useRef(null);
  const agentMeshesRef = useRef(new Map()); // id -> Group
  const linkLinesRef = useRef([]); // array of Line objects
  const particleBurstRef = useRef([]); // active spawn particles
  const targetLookAtRef = useRef(new THREE.Vector3(0, 0, 0));
  const currentLookAtRef = useRef(new THREE.Vector3(0, 0, 0));

  // Orbit controls state
  const isDraggingRef = useRef(false);
  const prevMousePosRef = useRef({ x: 0, y: 0 });
  const cameraOrbitRef = useRef({ theta: 0.3, phi: Math.PI / 3.5, radius: 38 });

  // ─── INIT: Scene, Camera, Renderer, Lights, Starfield ──────────
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    // 1. Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#04060C');
    scene.fog = new THREE.FogExp2('#04060C', 0.009);
    sceneRef.current = scene;

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(
      52,
      container.clientWidth / container.clientHeight,
      0.1,
      1200
    );
    camera.position.set(0, 30, 60);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    // 3. WebGL Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 4. Lights
    scene.add(new THREE.AmbientLight('#1a2744', 2.2));

    const mainLight = new THREE.DirectionalLight('#CBD5E1', 1.6);
    mainLight.position.set(25, 50, 20);
    scene.add(mainLight);

    const cyanPoint = new THREE.PointLight('#00F0FF', 4, 80);
    cyanPoint.position.set(-20, 15, -18);
    scene.add(cyanPoint);

    const purplePoint = new THREE.PointLight('#A855F7', 3.5, 80);
    purplePoint.position.set(22, 18, 14);
    scene.add(purplePoint);

    const emeraldPoint = new THREE.PointLight('#10B981', 2, 60);
    emeraldPoint.position.set(0, 8, -30);
    scene.add(emeraldPoint);

    // 5. Enhanced Starfield
    const starCount = 1200;
    const starGeo = new THREE.BufferGeometry();
    const starPos = new Float32Array(starCount * 3);
    const starSizes = new Float32Array(starCount);
    for (let i = 0; i < starCount; i++) {
      starPos[i * 3] = (Math.random() - 0.5) * 300;
      starPos[i * 3 + 1] = (Math.random() - 0.5) * 180 + 30;
      starPos[i * 3 + 2] = (Math.random() - 0.5) * 300;
      starSizes[i] = Math.random() * 1.8 + 0.3;
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
    starGeo.setAttribute('size', new THREE.BufferAttribute(starSizes, 1));
    const starMat = new THREE.PointsMaterial({
      color: '#7dd3fc',
      size: 0.7,
      transparent: true,
      opacity: 0.45,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });
    const starField = new THREE.Points(starGeo, starMat);
    scene.add(starField);

    // Secondary warm dust layer
    const dustCount = 400;
    const dustGeo = new THREE.BufferGeometry();
    const dustPos = new Float32Array(dustCount * 3);
    for (let i = 0; i < dustCount; i++) {
      dustPos[i * 3] = (Math.random() - 0.5) * 250;
      dustPos[i * 3 + 1] = (Math.random() - 0.5) * 100 + 15;
      dustPos[i * 3 + 2] = (Math.random() - 0.5) * 250;
    }
    dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
    const dustMat = new THREE.PointsMaterial({
      color: '#A855F7',
      size: 0.5,
      transparent: true,
      opacity: 0.25,
      blending: THREE.AdditiveBlending,
    });
    const dustField = new THREE.Points(dustGeo, dustMat);
    scene.add(dustField);

    // 6. Holographic Cyber Grid Floor (multi-layer)
    const gridMain = new THREE.GridHelper(120, 60, '#00F0FF', '#0F172A');
    gridMain.position.y = -3;
    gridMain.material.opacity = 0.22;
    gridMain.material.transparent = true;
    scene.add(gridMain);

    const gridSub = new THREE.GridHelper(120, 120, '#6366F1', '#0F172A');
    gridSub.position.y = -3.05;
    gridSub.material.opacity = 0.08;
    gridSub.material.transparent = true;
    scene.add(gridSub);

    // 7. Raycaster for Agent Clicking
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onPointerDown = (e) => {
      isDraggingRef.current = true;
      prevMousePosRef.current = { x: e.clientX, y: e.clientY };
    };

    const onPointerMove = (e) => {
      if (!isDraggingRef.current) return;
      const dx = e.clientX - prevMousePosRef.current.x;
      const dy = e.clientY - prevMousePosRef.current.y;
      prevMousePosRef.current = { x: e.clientX, y: e.clientY };

      cameraOrbitRef.current.theta -= dx * 0.005;
      cameraOrbitRef.current.phi = Math.max(
        0.15,
        Math.min(Math.PI / 2 - 0.05, cameraOrbitRef.current.phi - dy * 0.005)
      );
    };

    const onPointerUp = () => {
      isDraggingRef.current = false;
    };

    const onClick = (e) => {
      const rect = container.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / container.clientWidth) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / container.clientHeight) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const meshes = [];
      agentMeshesRef.current.forEach((group) => {
        group.traverse((child) => {
          if (child.isMesh) meshes.push(child);
        });
      });

      const intersects = raycaster.intersectObjects(meshes);
      if (intersects.length > 0) {
        let current = intersects[0].object;
        while (current && !current.userData?.agentId && current.parent) {
          current = current.parent;
        }
        if (current?.userData?.agentId) {
          onSelectAgent(current.userData.agentId);
        }
      }
    };

    const onWheel = (e) => {
      cameraOrbitRef.current.radius = Math.max(
        18,
        Math.min(100, cameraOrbitRef.current.radius + e.deltaY * 0.04)
      );
    };

    container.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    container.addEventListener('click', onClick);
    container.addEventListener('wheel', onWheel, { passive: true });

    // 8. Resize Handler
    const handleResize = () => {
      if (!container || !renderer || !camera) return;
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };
    window.addEventListener('resize', handleResize);

    // 9. Animation Loop
    let animationFrameId;
    const clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      const delta = clock.getDelta();
      const elapsed = clock.getElapsedTime();

      // Rotate starfield slowly
      starField.rotation.y = elapsed * 0.012;
      dustField.rotation.y = -elapsed * 0.008;

      // Animate agent pods
      agentMeshesRef.current.forEach((group, id) => {
        const isSelected = id === selectedAgentId;
        const speed = isSelected ? 2.0 : 1.0;

        // Core rotation + bobbing
        if (group.userData.core) {
          group.userData.core.rotation.y += delta * 0.7 * speed;
          group.userData.core.rotation.x += delta * 0.35 * speed;
          group.userData.core.position.y =
            Math.sin(elapsed * 1.8 + group.userData.phase) * 0.3 + 1.6;
        }

        // Gyroscope outer ring
        if (group.userData.outerRing) {
          group.userData.outerRing.rotation.x += delta * 1.1 * speed;
          group.userData.outerRing.rotation.y += delta * 0.55 * speed;
        }

        // Gyroscope inner ring
        if (group.userData.innerRing) {
          group.userData.innerRing.rotation.y -= delta * 1.4 * speed;
          group.userData.innerRing.rotation.z += delta * 0.7 * speed;
        }

        // Pulsing halo
        if (group.userData.halo) {
          const pulse = 1 + Math.sin(elapsed * 3.5 + group.userData.phase) * 0.1;
          group.userData.halo.scale.set(pulse, pulse, pulse);
        }

        // Breathing scale on entire group
        const breath = 1 + Math.sin(elapsed * 1.2 + group.userData.phase * 2) * 0.025;
        group.scale.set(breath, breath, breath);

        // Label always faces camera (sprites do this automatically)
        if (group.userData.label) {
          group.userData.label.material.opacity =
            isSelected ? 1.0 : 0.65 + Math.sin(elapsed * 2 + group.userData.phase) * 0.1;
        }
      });

      // Animate particle bursts
      for (let i = particleBurstRef.current.length - 1; i >= 0; i--) {
        const pGroup = particleBurstRef.current[i];
        pGroup.userData.age += delta;
        pGroup.children.forEach((p) => {
          p.position.addScaledVector(p.userData.velocity, delta);
          p.material.opacity = Math.max(0, 1 - pGroup.userData.age / 2.0);
          p.scale.multiplyScalar(0.995);
        });
        if (pGroup.userData.age > 2.0) {
          scene.remove(pGroup);
          particleBurstRef.current.splice(i, 1);
        }
      }

      // Smooth Camera Positioning (orbital)
      const { theta, phi, radius } = cameraOrbitRef.current;
      const targetCamX =
        currentLookAtRef.current.x + radius * Math.sin(phi) * Math.sin(theta);
      const targetCamY = currentLookAtRef.current.y + radius * Math.cos(phi);
      const targetCamZ =
        currentLookAtRef.current.z + radius * Math.sin(phi) * Math.cos(theta);

      camera.position.lerp(
        new THREE.Vector3(targetCamX, targetCamY, targetCamZ),
        0.065
      );
      currentLookAtRef.current.lerp(targetLookAtRef.current, 0.065);
      camera.lookAt(currentLookAtRef.current);

      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', handleResize);
      container.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      container.removeEventListener('click', onClick);
      container.removeEventListener('wheel', onWheel);
      if (renderer.domElement && container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, []);

  // ─── UPDATE: Build / Refresh Agent Pods when data changes ──────
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    // 1. ── Layout algorithm ──────────────────────────────────────
    //    Roots via Fibonacci spiral, children orbit their parent.
    const positions = new Map(); // id -> THREE.Vector3
    const roots = agents.filter((ag) => !ag.parent_agent_id);
    const children = agents.filter((ag) => ag.parent_agent_id);

    // Place roots on a Fibonacci disc
    roots.forEach((root, idx) => {
      positions.set(root.id, fibonacciDiscPosition(idx, roots.length, 4, 4.5));
    });

    // Place children around their parent in a smaller orbit
    const childrenByParent = new Map();
    children.forEach((child) => {
      if (!childrenByParent.has(child.parent_agent_id)) {
        childrenByParent.set(child.parent_agent_id, []);
      }
      childrenByParent.get(child.parent_agent_id).push(child);
    });

    childrenByParent.forEach((kids, parentId) => {
      const parentPos = positions.get(parentId);
      if (!parentPos) {
        // Parent not in roots — place children via fibonacci fallback
        kids.forEach((kid, idx) => {
          positions.set(
            kid.id,
            fibonacciDiscPosition(
              roots.length + idx,
              roots.length + kids.length,
              4,
              4.5
            )
          );
        });
        return;
      }
      const kidCount = kids.length;
      kids.forEach((kid, idx) => {
        const angle = (idx / kidCount) * Math.PI * 2 + Math.PI / 6;
        const orbitR = 10 + kidCount * 1.2;
        positions.set(
          kid.id,
          new THREE.Vector3(
            parentPos.x + Math.cos(angle) * orbitR,
            0,
            parentPos.z + Math.sin(angle) * orbitR
          )
        );
      });
    });

    // Fallback for orphans (neither root nor assigned child)
    agents.forEach((ag) => {
      if (!positions.has(ag.id)) {
        positions.set(
          ag.id,
          fibonacciDiscPosition(positions.size, agents.length, 4, 4.5)
        );
      }
    });

    // 2. ── Create / update 3D pods ──────────────────────────────
    const currentIds = new Set(agentMeshesRef.current.keys());
    const newIds = new Set(agents.map((ag) => ag.id));

    // Remove deleted
    currentIds.forEach((id) => {
      if (!newIds.has(id)) {
        const g = agentMeshesRef.current.get(id);
        scene.remove(g);
        agentMeshesRef.current.delete(id);
      }
    });

    agents.forEach((agent) => {
      const pos = positions.get(agent.id) || new THREE.Vector3(0, 0, 0);
      let agentGroup = agentMeshesRef.current.get(agent.id);

      const isOrchestrator =
        !agent.parent_agent_id ||
        (agent.role || '').toLowerCase().includes('orchestrator');
      const isRunning = agent.current_status === 'RUNNING';
      const isSelected = agent.id === selectedAgentId;
      const primaryColor = roleToColor(agent);

      if (!agentGroup) {
        // ── Build new 3D Agent Pod ──
        agentGroup = new THREE.Group();
        agentGroup.userData = {
          agentId: agent.id,
          phase: Math.random() * Math.PI * 2,
        };

        // A. Holographic Pedestal
        const baseGeo = new THREE.CylinderGeometry(2.0, 2.3, 0.35, 28);
        const baseMat = new THREE.MeshStandardMaterial({
          color: '#0F172A',
          metalness: 0.85,
          roughness: 0.15,
        });
        const base = new THREE.Mesh(baseGeo, baseMat);
        base.position.y = -1.8;
        agentGroup.add(base);

        // Neon base rim
        const rimGeo = new THREE.TorusGeometry(2.2, 0.07, 12, 36);
        const rimMat = new THREE.MeshBasicMaterial({ color: primaryColor });
        const rim = new THREE.Mesh(rimGeo, rimMat);
        rim.rotation.x = Math.PI / 2;
        rim.position.y = -1.6;
        agentGroup.add(rim);

        // B. Gyroscopic Outer Ring
        const outerRingGeo = new THREE.TorusGeometry(1.5, 0.07, 16, 44);
        const outerRingMat = new THREE.MeshStandardMaterial({
          color: primaryColor,
          emissive: primaryColor,
          emissiveIntensity: 0.5,
          metalness: 0.9,
          roughness: 0.1,
        });
        const outerRing = new THREE.Mesh(outerRingGeo, outerRingMat);
        agentGroup.add(outerRing);
        agentGroup.userData.outerRing = outerRing;

        // C. Gyroscopic Inner Ring
        const innerRingGeo = new THREE.TorusGeometry(1.1, 0.05, 16, 36);
        const innerRingMat = new THREE.MeshStandardMaterial({
          color: '#FFFFFF',
          emissive: primaryColor,
          emissiveIntensity: 0.7,
          metalness: 0.95,
        });
        const innerRing = new THREE.Mesh(innerRingGeo, innerRingMat);
        agentGroup.add(innerRing);
        agentGroup.userData.innerRing = innerRing;

        // D. Central Energy Core
        const coreGeo = isOrchestrator
          ? new THREE.IcosahedronGeometry(0.8, 1)
          : new THREE.OctahedronGeometry(0.7, 0);
        const coreMat = new THREE.MeshStandardMaterial({
          color: '#FFFFFF',
          emissive: primaryColor,
          emissiveIntensity: 0.9,
          roughness: 0.08,
          metalness: 0.7,
        });
        const core = new THREE.Mesh(coreGeo, coreMat);
        agentGroup.add(core);
        agentGroup.userData.core = core;

        // Wireframe shell
        const wireGeo = new THREE.IcosahedronGeometry(0.92, 1);
        const wireMat = new THREE.MeshBasicMaterial({
          color: primaryColor,
          wireframe: true,
          transparent: true,
          opacity: 0.4,
        });
        core.add(new THREE.Mesh(wireGeo, wireMat));

        // E. Status Beacon (top)
        const beaconGeo = new THREE.SphereGeometry(0.18, 12, 12);
        const beaconMat = new THREE.MeshBasicMaterial({ color: primaryColor });
        const beacon = new THREE.Mesh(beaconGeo, beaconMat);
        beacon.position.y = 3.0;
        agentGroup.add(beacon);

        // F. Halo selection ring (ground level)
        const haloGeo = new THREE.RingGeometry(2.4, 2.7, 36);
        const haloMat = new THREE.MeshBasicMaterial({
          color: primaryColor,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.35,
        });
        const halo = new THREE.Mesh(haloGeo, haloMat);
        halo.rotation.x = Math.PI / 2;
        halo.position.y = -1.9;
        agentGroup.add(halo);
        agentGroup.userData.halo = halo;

        // G. Floating Label Sprite
        const displayName =
          agent.name.length > 22
            ? agent.name.slice(0, 20) + '…'
            : agent.name;
        const label = createLabelSprite(displayName, primaryColor);
        label.position.y = 4.4;
        agentGroup.add(label);
        agentGroup.userData.label = label;

        scene.add(agentGroup);
        agentMeshesRef.current.set(agent.id, agentGroup);
      }

      // ── Update position (smooth lerp) ──
      const target = pos.clone();
      agentGroup.position.lerp(target, 0.12);
      // On first placement, snap
      if (agentGroup.position.lengthSq() === 0) {
        agentGroup.position.copy(target);
      }

      // ── Update halo visibility ──
      if (agentGroup.userData.halo) {
        agentGroup.userData.halo.visible = isSelected || isRunning;
        agentGroup.userData.halo.material.color.set(
          isSelected ? '#00F0FF' : primaryColor
        );
        agentGroup.userData.halo.material.opacity = isSelected ? 0.55 : 0.3;
      }

      // ── Update label opacity for selection ──
      if (agentGroup.userData.label) {
        agentGroup.userData.label.scale.set(
          ...(isSelected
            ? [agentGroup.userData.label.scale.x * 1, 1.8, 1]
            : [agentGroup.userData.label.scale.x * 1, 1.6, 1])
        );
      }
    });

    // 3. ── Render laser energy beams (Parent → Child) ──────────
    linkLinesRef.current.forEach((line) => scene.remove(line));
    linkLinesRef.current = [];

    agents.forEach((ag) => {
      if (
        ag.parent_agent_id &&
        positions.has(ag.parent_agent_id) &&
        positions.has(ag.id)
      ) {
        const p1 = positions.get(ag.parent_agent_id);
        const p2 = positions.get(ag.id);
        const mid = new THREE.Vector3(
          (p1.x + p2.x) / 2,
          4.5,
          (p1.z + p2.z) / 2
        );

        const curve = new THREE.CatmullRomCurve3([
          new THREE.Vector3(p1.x, 1.5, p1.z),
          mid,
          new THREE.Vector3(p2.x, 1.5, p2.z),
        ]);
        // Corde / Faisceau d'énergie 3D lumineuse entre l'Orchestrateur et le sous-agent
        const tubeGeo = new THREE.TubeGeometry(curve, 36, 0.09, 8, false);
        const tubeMat = new THREE.MeshStandardMaterial({
          color: '#00F0FF',
          emissive: '#00F0FF',
          emissiveIntensity: 1.8,
          roughness: 0.2,
          metalness: 0.8,
          transparent: true,
          opacity: 0.85,
        });
        const rope = new THREE.Mesh(tubeGeo, tubeMat);
        scene.add(rope);
        linkLinesRef.current.push(rope);
      }
    });
  }, [agents, selectedAgentId]);

  // ─── Spawn Particle Burst ──────────────────────────────────────
  useEffect(() => {
    if (!spawnEvent || !sceneRef.current) return;
    const scene = sceneRef.current;
    const mesh = agentMeshesRef.current.get(spawnEvent.agentId);
    if (!mesh) return;

    const pGroup = new THREE.Group();
    pGroup.position.copy(mesh.position);
    pGroup.userData = { age: 0 };

    const colors = ['#00F0FF', '#A855F7', '#10B981', '#6366F1'];
    const count = 55;
    for (let i = 0; i < count; i++) {
      const geo = new THREE.SphereGeometry(0.1 + Math.random() * 0.08, 6, 6);
      const mat = new THREE.MeshBasicMaterial({
        color: colors[i % colors.length],
        transparent: true,
        opacity: 1,
      });
      const p = new THREE.Mesh(geo, mat);
      const velocity = new THREE.Vector3(
        (Math.random() - 0.5) * 16,
        Math.random() * 10 + 3,
        (Math.random() - 0.5) * 16
      );
      p.userData = { velocity };
      pGroup.add(p);
    }
    scene.add(pGroup);
    particleBurstRef.current.push(pGroup);
  }, [spawnEvent]);

  // ─── Camera Focus on Selected Agent ────────────────────────────
  useEffect(() => {
    if (!selectedAgentId) {
      targetLookAtRef.current.set(0, 0, 0);
      cameraOrbitRef.current.radius = 38;
      return;
    }
    const mesh = agentMeshesRef.current.get(selectedAgentId);
    if (mesh) {
      targetLookAtRef.current.copy(mesh.position);
      cameraOrbitRef.current.radius = 26;
    }
  }, [selectedAgentId]);

  return (
    <div
      ref={mountRef}
      className={`canvas-wrapper ${isSplitView ? 'split' : ''}`}
      style={{ cursor: isDraggingRef.current ? 'grabbing' : 'grab' }}
    />
  );
}
