import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

/**
 * ThreeCanvas — Composant de rendu 3D temps réel avec Three.js
 * Visualise l'univers multi-agents, les miniatures 3D de pods, les lasers
 * de parentage, les particules de spawn et la caméra orbitale interactive.
 */
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
  const targetCameraPosRef = useRef(new THREE.Vector3(0, 18, 38));
  const targetLookAtRef = useRef(new THREE.Vector3(0, 0, 0));
  const currentLookAtRef = useRef(new THREE.Vector3(0, 0, 0));

  // Controls state
  const isDraggingRef = useRef(false);
  const prevMousePosRef = useRef({ x: 0, y: 0 });
  const cameraOrbitRef = useRef({ theta: 0, phi: Math.PI / 4, radius: 42 });

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    // 1. Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#05070E');
    scene.fog = new THREE.FogExp2('#05070E', 0.015);
    sceneRef.current = scene;

    // 2. Camera setup
    const camera = new THREE.PerspectiveCamera(
      55,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );
    camera.position.set(0, 22, 45);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    // 3. WebGL Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 4. Lights
    const ambientLight = new THREE.AmbientLight('#263859', 1.8);
    scene.add(ambientLight);

    const mainLight = new THREE.DirectionalLight('#E2E8F0', 1.5);
    mainLight.position.set(20, 40, 20);
    scene.add(mainLight);

    const cyanPoint = new THREE.PointLight('#00F0FF', 3, 50);
    cyanPoint.position.set(-15, 10, -10);
    scene.add(cyanPoint);

    const purplePoint = new THREE.PointLight('#A855F7', 2.5, 50);
    purplePoint.position.set(15, 12, 10);
    scene.add(purplePoint);

    // 5. Starfield Dust Particles
    const starCount = 800;
    const starGeo = new THREE.BufferGeometry();
    const starPositions = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount * 3; i += 3) {
      starPositions[i] = (Math.random() - 0.5) * 200;
      starPositions[i + 1] = (Math.random() - 0.5) * 120 + 20;
      starPositions[i + 2] = (Math.random() - 0.5) * 200;
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
    const starMat = new THREE.PointsMaterial({
      color: '#00F0FF',
      size: 0.8,
      transparent: true,
      opacity: 0.5,
      blending: THREE.AdditiveBlending,
    });
    const starField = new THREE.Points(starGeo, starMat);
    scene.add(starField);

    // 6. Holographic Cyber Grid Floor
    const gridHelper = new THREE.GridHelper(90, 45, '#00F0FF', '#1E293B');
    gridHelper.position.y = -2;
    gridHelper.material.opacity = 0.28;
    gridHelper.material.transparent = true;
    scene.add(gridHelper);

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
        0.1,
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
        15,
        Math.min(80, cameraOrbitRef.current.radius + e.deltaY * 0.03)
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
    let clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      const delta = clock.getDelta();
      const elapsed = clock.getElapsedTime();

      // Rotate starfield slowly
      starField.rotation.y = elapsed * 0.015;

      // Rotate agent miniatures & gyroscopes
      agentMeshesRef.current.forEach((group, id) => {
        const isSelected = id === selectedAgentId;
        const speed = isSelected ? 1.8 : 1.0;

        // Core gentle bobbing
        if (group.userData.core) {
          group.userData.core.rotation.y += delta * 0.8 * speed;
          group.userData.core.rotation.x += delta * 0.4 * speed;
          group.userData.core.position.y = Math.sin(elapsed * 2 + group.userData.phase) * 0.25 + 1.6;
        }

        // Gyroscope outer ring
        if (group.userData.outerRing) {
          group.userData.outerRing.rotation.x += delta * 1.2 * speed;
          group.userData.outerRing.rotation.y += delta * 0.6 * speed;
        }

        // Gyroscope inner ring
        if (group.userData.innerRing) {
          group.userData.innerRing.rotation.y -= delta * 1.5 * speed;
          group.userData.innerRing.rotation.z += delta * 0.8 * speed;
        }

        // Pulsing halo for RUNNING or selected
        if (group.userData.halo) {
          const scale = 1 + Math.sin(elapsed * 4) * 0.08;
          group.userData.halo.scale.set(scale, scale, scale);
        }
      });

      // Animate particle bursts
      for (let i = particleBurstRef.current.length - 1; i >= 0; i--) {
        const pGroup = particleBurstRef.current[i];
        pGroup.userData.age += delta;
        pGroup.children.forEach((p) => {
          p.position.addScaledVector(p.userData.velocity, delta);
          p.material.opacity = Math.max(0, 1 - pGroup.userData.age / 1.5);
        });
        if (pGroup.userData.age > 1.5) {
          scene.remove(pGroup);
          particleBurstRef.current.splice(i, 1);
        }
      }

      // Smooth Camera Positioning
      const { theta, phi, radius } = cameraOrbitRef.current;
      const targetCamX = currentLookAtRef.current.x + radius * Math.sin(phi) * Math.sin(theta);
      const targetCamY = currentLookAtRef.current.y + radius * Math.cos(phi);
      const targetCamZ = currentLookAtRef.current.z + radius * Math.sin(phi) * Math.cos(theta);

      camera.position.lerp(new THREE.Vector3(targetCamX, targetCamY, targetCamZ), 0.08);
      currentLookAtRef.current.lerp(targetLookAtRef.current, 0.08);
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
      if (renderer.domElement) {
        container.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, []);

  // Update Agent 3D Miniatures when agents list changes
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    // 1. Position layout calculation (hierarchical constellation)
    const agentMap = new Map();
    agents.forEach((ag) => agentMap.set(ag.id, ag));

    // Find roots (agents without parent or orchestrator)
    const roots = agents.filter((ag) => !ag.parent_agent_id);
    const positions = new Map(); // id -> THREE.Vector3

    // Position roots in inner ring
    const rootCount = Math.max(1, roots.length);
    roots.forEach((root, idx) => {
      const angle = (idx / rootCount) * Math.PI * 2;
      const radius = rootCount === 1 ? 0 : 8;
      positions.set(root.id, new THREE.Vector3(Math.cos(angle) * radius, 0, Math.sin(angle) * radius));
    });

    // Position children around their respective parent
    agents.forEach((ag) => {
      if (ag.parent_agent_id && positions.has(ag.parent_agent_id)) {
        const parentPos = positions.get(ag.parent_agent_id);
        const siblings = agents.filter((x) => x.parent_agent_id === ag.parent_agent_id);
        const childIdx = siblings.findIndex((x) => x.id === ag.id);
        const childAngle = (childIdx / siblings.length) * Math.PI * 2;
        const childRadius = 14;
        positions.set(
          ag.id,
          new THREE.Vector3(
            parentPos.x + Math.cos(childAngle) * childRadius,
            0,
            parentPos.z + Math.sin(childAngle) * childRadius
          )
        );
      } else if (!positions.has(ag.id)) {
        // Default scattered placement
        const angle = Math.random() * Math.PI * 2;
        positions.set(ag.id, new THREE.Vector3(Math.cos(angle) * 16, 0, Math.sin(angle) * 16));
      }
    });

    // 2. Build or update 3D Meshes for each Agent
    const currentMeshIds = new Set(agentMeshesRef.current.keys());
    const newMeshIds = new Set(agents.map((ag) => ag.id));

    // Remove deleted agents
    currentMeshIds.forEach((id) => {
      if (!newMeshIds.has(id)) {
        const mesh = agentMeshesRef.current.get(id);
        scene.remove(mesh);
        agentMeshesRef.current.delete(id);
      }
    });

    // Create or update agents
    agents.forEach((agent) => {
      const pos = positions.get(agent.id) || new THREE.Vector3(0, 0, 0);
      let agentGroup = agentMeshesRef.current.get(agent.id);

      const isOrchestrator = !agent.parent_agent_id || agent.role?.toLowerCase().includes('orchestrator');
      const isRunning = agent.current_status === 'RUNNING';
      const isSelected = agent.id === selectedAgentId;

      const primaryColor = isRunning
        ? '#10B981' // Green
        : isOrchestrator
        ? '#00F0FF' // Cyan
        : agent.role?.toLowerCase().includes('security')
        ? '#F59E0B' // Amber
        : '#A855F7'; // Purple

      if (!agentGroup) {
        // Create new 3D Agent Miniature Pod
        agentGroup = new THREE.Group();
        agentGroup.userData = {
          agentId: agent.id,
          phase: Math.random() * Math.PI,
        };

        // A. Holographic Pedestal / Base Ring
        const baseGeo = new THREE.CylinderGeometry(2.2, 2.5, 0.4, 24);
        const baseMat = new THREE.MeshStandardMaterial({
          color: '#0F172A',
          metalness: 0.8,
          roughness: 0.2,
        });
        const base = new THREE.Mesh(baseGeo, baseMat);
        base.position.y = -1.8;
        agentGroup.add(base);

        // Neon base rim
        const rimGeo = new THREE.TorusGeometry(2.4, 0.08, 12, 32);
        const rimMat = new THREE.MeshBasicMaterial({ color: primaryColor });
        const rim = new THREE.Mesh(rimGeo, rimMat);
        rim.rotation.x = Math.PI / 2;
        rim.position.y = -1.6;
        agentGroup.add(rim);

        // B. Gyroscopic Outer Ring
        const outerRingGeo = new THREE.TorusGeometry(1.6, 0.08, 16, 40);
        const outerRingMat = new THREE.MeshStandardMaterial({
          color: primaryColor,
          emissive: primaryColor,
          emissiveIntensity: 0.4,
          metalness: 0.9,
          roughness: 0.1,
        });
        const outerRing = new THREE.Mesh(outerRingGeo, outerRingMat);
        agentGroup.add(outerRing);
        agentGroup.userData.outerRing = outerRing;

        // C. Gyroscopic Inner Ring
        const innerRingGeo = new THREE.TorusGeometry(1.2, 0.06, 16, 32);
        const innerRingMat = new THREE.MeshStandardMaterial({
          color: '#FFFFFF',
          emissive: primaryColor,
          emissiveIntensity: 0.6,
          metalness: 0.95,
        });
        const innerRing = new THREE.Mesh(innerRingGeo, innerRingMat);
        agentGroup.add(innerRing);
        agentGroup.userData.innerRing = innerRing;

        // D. Central Cybernetic Energy Core
        const coreGeo = isOrchestrator
          ? new THREE.IcosahedronGeometry(0.85, 1)
          : new THREE.OctahedronGeometry(0.75, 0);
        const coreMat = new THREE.MeshStandardMaterial({
          color: '#FFFFFF',
          emissive: primaryColor,
          emissiveIntensity: 0.8,
          roughness: 0.1,
          metalness: 0.7,
          wireframe: false,
        });
        const core = new THREE.Mesh(coreGeo, coreMat);
        agentGroup.add(core);
        agentGroup.userData.core = core;

        // Wireframe shell for core
        const wireGeo = new THREE.IcosahedronGeometry(0.98, 1);
        const wireMat = new THREE.MeshBasicMaterial({
          color: primaryColor,
          wireframe: true,
          transparent: true,
          opacity: 0.45,
        });
        const wireShell = new THREE.Mesh(wireGeo, wireMat);
        core.add(wireShell);

        // E. Floating Status Beacon
        const beaconGeo = new THREE.SphereGeometry(0.2, 12, 12);
        const beaconMat = new THREE.MeshBasicMaterial({ color: primaryColor });
        const beacon = new THREE.Mesh(beaconGeo, beaconMat);
        beacon.position.y = 3.2;
        agentGroup.add(beacon);

        // F. Halo selection ring
        const haloGeo = new THREE.RingGeometry(2.6, 2.9, 32);
        const haloMat = new THREE.MeshBasicMaterial({
          color: primaryColor,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.4,
        });
        const halo = new THREE.Mesh(haloGeo, haloMat);
        halo.rotation.x = Math.PI / 2;
        halo.position.y = -1.9;
        agentGroup.add(halo);
        agentGroup.userData.halo = halo;

        scene.add(agentGroup);
        agentMeshesRef.current.set(agent.id, agentGroup);
      }

      // Smooth position placement
      agentGroup.position.copy(pos);

      // Highlight if selected
      if (agentGroup.userData.halo) {
        agentGroup.userData.halo.visible = isSelected || isRunning;
        agentGroup.userData.halo.material.color.set(isSelected ? '#00F0FF' : primaryColor);
      }
    });

    // 3. Render 3D Laser Energy Beams (Parent -> Child links)
    // Remove old lines
    linkLinesRef.current.forEach((line) => scene.remove(line));
    linkLinesRef.current = [];

    agents.forEach((ag) => {
      if (ag.parent_agent_id && positions.has(ag.parent_agent_id) && positions.has(ag.id)) {
        const p1 = positions.get(ag.parent_agent_id);
        const p2 = positions.get(ag.id);

        const points = [
          new THREE.Vector3(p1.x, 1.5, p1.z),
          new THREE.Vector3((p1.x + p2.x) / 2, 3.5, (p1.z + p2.z) / 2),
          new THREE.Vector3(p2.x, 1.5, p2.z),
        ];
        const curve = new THREE.CatmullRomCurve3(points);
        const curvePoints = curve.getPoints(30);
        const lineGeo = new THREE.BufferGeometry().setFromPoints(curvePoints);

        const lineMat = new THREE.LineBasicMaterial({
          color: '#00F0FF',
          transparent: true,
          opacity: 0.65,
          linewidth: 2,
        });
        const line = new THREE.Line(lineGeo, lineMat);
        scene.add(line);
        linkLinesRef.current.push(line);
      }
    });
  }, [agents, selectedAgentId]);

  // Handle Dynamic Spawning Explosion / Particle Burst
  useEffect(() => {
    if (!spawnEvent || !sceneRef.current) return;
    const scene = sceneRef.current;
    const mesh = agentMeshesRef.current.get(spawnEvent.agentId);
    if (!mesh) return;

    // Create particle explosion at spawn position
    const pGroup = new THREE.Group();
    pGroup.position.copy(mesh.position);
    pGroup.userData = { age: 0 };

    const count = 40;
    for (let i = 0; i < count; i++) {
      const geo = new THREE.SphereGeometry(0.12, 6, 6);
      const mat = new THREE.MeshBasicMaterial({
        color: '#00F0FF',
        transparent: true,
        opacity: 1,
      });
      const p = new THREE.Mesh(geo, mat);
      const velocity = new THREE.Vector3(
        (Math.random() - 0.5) * 14,
        Math.random() * 8 + 2,
        (Math.random() - 0.5) * 14
      );
      p.userData = { velocity };
      pGroup.add(p);
    }
    scene.add(pGroup);
    particleBurstRef.current.push(pGroup);
  }, [spawnEvent]);

  // Focus Camera on Selected Agent
  useEffect(() => {
    if (!selectedAgentId) {
      targetLookAtRef.current.set(0, 0, 0);
      return;
    }
    const mesh = agentMeshesRef.current.get(selectedAgentId);
    if (mesh) {
      targetLookAtRef.current.copy(mesh.position);
      cameraOrbitRef.current.radius = 24; // Smooth zoom-in
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
