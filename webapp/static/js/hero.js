// Home page hero: a slowly turning gold trophy with drifting gold particles.
// Loaded only on Home, after three.js (pinned r128 from cdnjs). Falls back to
// the static SVG trophy already in the page when WebGL or three.js is missing.
(function () {
  "use strict";

  var mount = document.getElementById("hero3d");
  var fallback = document.getElementById("heroFallback");
  if (!mount) return;

  function webglAvailable() {
    try {
      var c = document.createElement("canvas");
      return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
    } catch (e) {
      return false;
    }
  }
  if (!window.THREE || !webglAvailable()) return; // keep the static fallback

  var THREE = window.THREE;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var small = window.matchMedia("(max-width: 640px)").matches;

  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: !small, alpha: true, powerPreference: "low-power" });
  } catch (e) {
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, small ? 1.25 : 1.75));
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.domElement.setAttribute("aria-hidden", "true");
  renderer.domElement.className = "block h-full w-full";

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  camera.position.set(0, 0.35, 7);
  camera.lookAt(0, -0.1, 0);

  // A warm studio environment for the metal to reflect (a cream-to-bronze
  // gradient dome with two bright "softbox" panels), so it reads as gold
  // rather than picking up the navy page around it.
  (function buildEnvironment() {
    var envScene = new THREE.Scene();
    var dome = new THREE.SphereGeometry(10, 32, 16);
    var colors = [];
    var pos = dome.attributes.position;
    var top = new THREE.Color("#FFF6E0"), mid = new THREE.Color("#8A6A35"), bottom = new THREE.Color("#1A1309");
    for (var i = 0; i < pos.count; i++) {
      var t = (pos.getY(i) / 10 + 1) / 2;
      var c = t > 0.5 ? mid.clone().lerp(top, (t - 0.5) * 2) : bottom.clone().lerp(mid, t * 2);
      colors.push(c.r, c.g, c.b);
    }
    dome.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    envScene.add(new THREE.Mesh(dome, new THREE.MeshBasicMaterial({ side: THREE.BackSide, vertexColors: true })));
    var panel = new THREE.MeshBasicMaterial({ color: 0xffffff });
    var key = new THREE.Mesh(new THREE.PlaneGeometry(6, 3), panel);
    key.position.set(-5, 3, 4); key.lookAt(0, 0, 0); envScene.add(key);
    var rim = new THREE.Mesh(new THREE.PlaneGeometry(2, 6), new THREE.MeshBasicMaterial({ color: 0xffe3a3 }));
    rim.position.set(6, 1, -3); rim.lookAt(0, 0, 0); envScene.add(rim);
    var pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(envScene, 0.03).texture;
    pmrem.dispose();
  })();

  scene.add(new THREE.AmbientLight(0xffffff, 0.25));
  var keyLight = new THREE.DirectionalLight(0xfff1d0, 1.4);
  keyLight.position.set(-3, 5, 4);
  scene.add(keyLight);
  var rimLight = new THREE.DirectionalLight(0x8fb0ff, 0.6);
  rimLight.position.set(4, 2, -4);
  scene.add(rimLight);

  var gold = new THREE.MeshStandardMaterial({ color: 0xf2c25a, metalness: 1, roughness: 0.22 });
  var goldSoft = new THREE.MeshStandardMaterial({ color: 0xe0ac44, metalness: 1, roughness: 0.32 });
  // Very dark base colour: the warm key light and ACES tone mapping lift dark
  // values a lot, so this is what renders as deep navy rather than slate.
  var navy = new THREE.MeshStandardMaterial({ color: 0x030712, metalness: 0, roughness: 0.75, envMapIntensity: 0.08 });

  var trophy = new THREE.Group();

  function lathe(points, material, segments) {
    var v = points.map(function (p) { return new THREE.Vector2(p[0], p[1]); });
    var mesh = new THREE.Mesh(new THREE.LatheGeometry(v, segments || 64), material);
    mesh.material.side = THREE.DoubleSide;
    return mesh;
  }

  // Cup, with a lip that folds back inside.
  var CUP_OUTER = [[0.0, -0.2], [0.22, -0.18], [0.5, 0.02], [0.72, 0.38], [0.86, 0.8], [0.92, 1.18]];
  trophy.add(lathe(CUP_OUTER.concat([
    [0.96, 1.24], [0.9, 1.26], [0.84, 1.16], [0.78, 0.82], [0.64, 0.46], [0.42, 0.18], [0.0, 0.08],
  ]), gold));

  // The cup's outer radius at height y (linear between the outline points),
  // so the handles can be anchored exactly on its curved surface.
  function cupRadiusAt(y) {
    for (var i = 1; i < CUP_OUTER.length; i++) {
      var a = CUP_OUTER[i - 1], b = CUP_OUTER[i];
      if (y <= b[1]) return a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]);
    }
    return CUP_OUTER[CUP_OUTER.length - 1][0];
  }
  // Stem and foot.
  trophy.add(lathe([
    [0.0, -1.0], [0.42, -1.0], [0.42, -0.94], [0.2, -0.86], [0.11, -0.7], [0.1, -0.45],
    [0.2, -0.36], [0.13, -0.28], [0.18, -0.2], [0.0, -0.2],
  ], gold));
  // Handles: a curved tube on each side whose two ends are anchored on the
  // cup's own surface (radius at that height, minus a small inset), so both
  // ends sit just inside the cup from every angle. The cup is narrower lower
  // down, which is why a plain half-ring left a gap at its lower end.
  var HANDLE_TOP_Y = 1.02, HANDLE_BOTTOM_Y = 0.3, HANDLE_TUBE = 0.055, INSET = 0.04;
  [-1, 1].forEach(function (side) {
    var topX = cupRadiusAt(HANDLE_TOP_Y) - INSET;
    var bottomX = cupRadiusAt(HANDLE_BOTTOM_Y) - INSET;
    var curve = new THREE.CubicBezierCurve3(
      new THREE.Vector3(side * topX, HANDLE_TOP_Y, 0),
      new THREE.Vector3(side * 1.32, HANDLE_TOP_Y + 0.08, 0),
      new THREE.Vector3(side * 1.22, HANDLE_BOTTOM_Y - 0.02, 0),
      new THREE.Vector3(side * bottomX, HANDLE_BOTTOM_Y, 0)
    );
    trophy.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 48, HANDLE_TUBE, 16, false), goldSoft));
  });
  // Emblem on the front of the cup: a polished gold star on a navy medallion,
  // so it reads clearly against the gold cup.
  (function () {
    var medallion = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.04, 48), navy);
    medallion.rotation.x = Math.PI / 2 + 0.3; // lean with the flared cup wall
    medallion.position.set(0, 0.68, 0.84);
    trophy.add(medallion);

    var star = new THREE.Shape();
    for (var i = 0; i < 10; i++) {
      var r = i % 2 === 0 ? 0.22 : 0.09;
      var a = Math.PI / 2 + (i * Math.PI) / 5;
      if (i === 0) star.moveTo(Math.cos(a) * r, Math.sin(a) * r);
      else star.lineTo(Math.cos(a) * r, Math.sin(a) * r);
    }
    var geo = new THREE.ExtrudeGeometry(star, { depth: 0.04, bevelEnabled: true, bevelSize: 0.014, bevelThickness: 0.014, bevelSegments: 3 });
    var starGold = new THREE.MeshStandardMaterial({
      color: 0xffc940, metalness: 1, roughness: 0.18, emissive: 0x4a3000, emissiveIntensity: 0.3,
    });
    var mesh = new THREE.Mesh(geo, starGold);
    mesh.position.set(0, 0.68, 0.86);
    mesh.rotation.x = 0.3;
    trophy.add(mesh);
  })();
  // Two-tier plinth with a gold plate.
  var plinth = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.42, 1.5), navy);
  plinth.position.y = -1.22;
  trophy.add(plinth);
  var plinthTop = new THREE.Mesh(new THREE.BoxGeometry(1.18, 0.16, 1.18), navy);
  plinthTop.position.y = -0.94;
  trophy.add(plinthTop);
  var plate = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.16, 0.02), goldSoft);
  plate.position.set(0, -1.22, 0.76);
  trophy.add(plate);

  trophy.position.y = -0.05;
  trophy.rotation.y = -0.5;
  scene.add(trophy);

  // Floating gold particles.
  var count = small ? 28 : 64;
  var positions = new Float32Array(count * 3);
  var speeds = new Float32Array(count);
  for (var i = 0; i < count; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 5;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 4.4;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 3 - 0.5;
    speeds[i] = 0.12 + Math.random() * 0.25;
  }
  var pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  var sprite = (function () {
    var c = document.createElement("canvas");
    c.width = c.height = 64;
    var g = c.getContext("2d");
    var grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0, "rgba(255,240,200,1)");
    grad.addColorStop(0.35, "rgba(228,190,99,0.8)");
    grad.addColorStop(1, "rgba(228,190,99,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  })();
  var particles = new THREE.Points(pGeo, new THREE.PointsMaterial({
    size: small ? 0.12 : 0.1, map: sprite, transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending, opacity: 0.9,
  }));
  scene.add(particles);

  mount.appendChild(renderer.domElement);
  if (fallback) fallback.hidden = true;

  function resize() {
    var w = mount.clientWidth, h = mount.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    if (!running) renderer.render(scene, camera);
  }

  var running = false, rafId = null, last = 0, elapsed = 0, visible = true;

  function frame(now) {
    var dt = Math.min(0.05, (now - last) / 1000 || 0);
    last = now;
    elapsed += dt;
    trophy.rotation.y += dt * 0.45;
    trophy.position.y = -0.05 + Math.sin(elapsed * 1.2) * 0.06;
    var arr = pGeo.attributes.position.array;
    for (var i = 0; i < count; i++) {
      arr[i * 3 + 1] += speeds[i] * dt;
      arr[i * 3] += Math.sin(elapsed + i) * 0.0015;
      if (arr[i * 3 + 1] > 2.3) arr[i * 3 + 1] = -2.3;
    }
    pGeo.attributes.position.needsUpdate = true;
    renderer.render(scene, camera);
    rafId = requestAnimationFrame(frame);
  }

  function play() {
    if (running || reduceMotion || document.hidden || !visible) return;
    running = true;
    last = performance.now();
    rafId = requestAnimationFrame(frame);
  }
  function pause() {
    running = false;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
  }

  if (window.ResizeObserver) new ResizeObserver(resize).observe(mount);
  else window.addEventListener("resize", resize);
  resize();

  // Pause when the tab is hidden or the hero is scrolled out of view.
  document.addEventListener("visibilitychange", function () { document.hidden ? pause() : play(); });
  if (window.IntersectionObserver) {
    new IntersectionObserver(function (entries) {
      visible = entries[0].isIntersecting;
      visible ? play() : pause();
    }).observe(mount);
  }

  renderer.render(scene, camera); // reduced motion: this still frame is all there is
  play();
})();
