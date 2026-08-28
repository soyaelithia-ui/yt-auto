/**
 * CameraController.js - WebGL Cinematic Camera Drift and Trauma Shake Engine.
 */
class CameraController {
  constructor(decayRate = 1.2, baseFov = 60.0) {
    this.decayRate = decayRate;
    this.baseFov = baseFov;
    this.trauma = 0.0;
  }

  pseudoPerlin(t, seed = 0.0) {
    return (
      Math.sin(t * 1.0 + seed) * 0.50 +
      Math.sin(t * 2.3 + seed * 1.7) * 0.25 +
      Math.sin(t * 4.7 + seed * 3.1) * 0.15 +
      Math.sin(t * 9.1 + seed * 5.9) * 0.10
    );
  }

  addTrauma(amount) {
    this.trauma = Math.min(1.0, this.trauma + Math.max(0.0, amount));
  }

  update(t, deltaSec = 0.033, seed = 42.0) {
    const driftX = this.pseudoPerlin(t * 0.18, seed) * 0.35;
    const driftY = this.pseudoPerlin(t * 0.14, seed + 10.0) * 0.25;
    const driftZ = -t * 0.45;
    const rotDriftZ = this.pseudoPerlin(t * 0.12, seed + 20.0) * 0.035;

    const shake = Math.pow(this.trauma, 2);
    let shakeX = 0.0;
    let shakeY = 0.0;
    let shakeRotZ = 0.0;

    if (shake > 0.001) {
      const freq = 32.0;
      shakeX = Math.sin(t * freq) * shake * 0.45;
      shakeY = Math.cos(t * freq * 1.3) * shake * 0.45;
      shakeRotZ = Math.sin(t * freq * 0.8) * shake * 0.08;
      this.trauma = Math.max(0.0, this.trauma - this.decayRate * deltaSec);
    }

    return {
      x: driftX + shakeX,
      y: driftY + shakeY,
      z: driftZ,
      rotZ: rotDriftZ + shakeRotZ,
      fov: this.baseFov + shake * 4.0,
    };
  }
}
