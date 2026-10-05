// The hero WebGL scene: requests flow through a gateway ring, and a few are turned away.
// Built with @react-three/fiber and @react-three/drei (MIT). The composition is original. It follows the
// "WebGL section" pattern from threeui.com (https://threeui.com, not reachable from this build container, so no code was copied).
// This module is only imported by hero-visual.tsx, after first paint, and never by anything under /app.
import { Float } from '@react-three/drei'
import { Canvas, useFrame } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'

const COUNT = 72

function unit(n: number): number {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453
  return x - Math.floor(x)
}

function cssColor(name: string, fallback: string): THREE.Color {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const c = new THREE.Color()
  try { c.set(v || fallback) } catch { c.set(fallback) }
  return c
}

function Requests() {
  const mesh = useRef<THREE.InstancedMesh>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const seeds = useMemo(
    () => Array.from({ length: COUNT }, (_, i) => ({
      x: (unit(i * 3 + 1) - 0.5) * 1.7,
      y: (unit(i * 3 + 2) - 0.5) * 1.7,
      speed: 0.12 + unit(i * 3 + 3) * 0.1,
      phase: unit(i * 5 + 9),
      denied: i % 7 === 0,
    })),
    [],
  )

  useLayoutEffect(() => {
    const m = mesh.current
    if (!m) return
    const allow = cssColor('--allow', '#4CD38A')
    const deny = cssColor('--deny', '#FF7A72')
    seeds.forEach((s, i) => m.setColorAt(i, s.denied ? deny : allow))
    if (m.instanceColor) m.instanceColor.needsUpdate = true
  }, [seeds])

  useFrame(({ clock }) => {
    const m = mesh.current
    if (!m) return
    const t = clock.elapsedTime
    seeds.forEach((s, i) => {
      const p = (t * s.speed + s.phase) % 1
      const z = p * 9 - 4.5
      let { x, y } = s
      let scale = 0.06
      if (s.denied && z > 0) {
        // A denied request is stopped at the ring and drifts outward.
        const k = Math.min(z / 4.5, 1)
        x += Math.sign(x || 1) * k * 2.2
        y += Math.sign(y || 1) * k * 1.4
        scale = 0.06 * (1 - k * 0.7)
      }
      dummy.position.set(x, y, z)
      dummy.scale.setScalar(scale)
      dummy.updateMatrix()
      m.setMatrixAt(i, dummy.matrix)
    })
    m.instanceMatrix.needsUpdate = true
  })

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, COUNT]}>
      <sphereGeometry args={[1, 12, 12]} />
      <meshBasicMaterial />
    </instancedMesh>
  )
}

function Gateway() {
  const ring = useMemo(() => cssColor('--brand', '#6E8BFF'), [])
  return (
    <Float speed={1.2} rotationIntensity={0.15} floatIntensity={0.3}>
      <mesh>
        <torusGeometry args={[1.35, 0.035, 16, 96]} />
        <meshBasicMaterial color={ring} />
      </mesh>
      <mesh scale={1.18}>
        <torusGeometry args={[1.35, 0.012, 8, 96]} />
        <meshBasicMaterial color={ring} transparent opacity={0.4} />
      </mesh>
    </Float>
  )
}

export default function HeroScene({ active }: { active: boolean }) {
  return (
    <Canvas
      dpr={[1, 1.5]}
      frameloop={active ? 'always' : 'never'}
      camera={{ position: [3.6, 1.4, 5.4], fov: 38 }}
      gl={{ alpha: true, antialias: true, powerPreference: 'low-power' }}
      aria-hidden="true"
      style={{ position: 'absolute', inset: 0 }}
    >
      <group rotation={[0, -0.35, 0]}>
        <Gateway />
        <Requests />
      </group>
    </Canvas>
  )
}
