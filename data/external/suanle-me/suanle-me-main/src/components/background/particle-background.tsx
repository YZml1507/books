"use client";

import { useEffect, useRef } from "react";

const trigrams = ["☰", "☱", "☲", "☳", "☴", "☵", "☶", "☷"];

export function ParticleBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }

    let width = window.innerWidth;
    let height = window.innerHeight;
    let animationFrame = 0;
    const particleCount = Math.min(90, Math.max(36, Math.floor(width / 18)));

    const particles = Array.from({ length: particleCount }, (_, index) => ({
      x: (index * 977) % width,
      y: (index * 613) % height,
      radius: 0.55 + ((index * 13) % 10) / 10,
      speed: 0.08 + ((index * 7) % 11) / 100,
      opacity: 0.2 + ((index * 17) % 9) / 20,
    }));

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * window.devicePixelRatio;
      canvas.height = height * window.devicePixelRatio;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
    };

    const draw = () => {
      context.clearRect(0, 0, width, height);
      particles.forEach((particle) => {
        particle.y -= particle.speed;
        particle.x += Math.sin((particle.y + particle.radius) * 0.004) * 0.05;

        if (particle.y < -8) {
          particle.y = height + 8;
          particle.x = (particle.x + 89) % width;
        }

        context.beginPath();
        context.fillStyle = `rgba(245, 241, 232, ${particle.opacity})`;
        context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
        context.fill();
      });

      animationFrame = window.requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener("resize", resize);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <canvas ref={canvasRef} className="absolute inset-0 opacity-60" />
      <div className="bagua-mark hidden sm:block">
        {trigrams.map((trigram, index) => (
          <span key={trigram} style={{ "--angle": `${index * 45}deg` } as React.CSSProperties}>
            {trigram}
          </span>
        ))}
        <div className="bagua-core">☯</div>
      </div>
    </div>
  );
}
