// Camera.cs — 第三人称轨道相机
using System;
using Farwalk.Engine;

namespace Farwalk.Game
{
    public class OrbitCamera
    {
        public Vec3 Target, Position, SmoothTarget;
        public float Yaw, Pitch, Distance = 5.2f, BaseDistance = 5.2f;
        public float Fov = 52f;
        public float HeightOffset = 1.55f;
        public float Sensitivity = 0.0034f;

        public OrbitCamera()
        {
            Target = new Vec3(0, 2, 0);
            SmoothTarget = new Vec3(0, 2, 0);
            Position = new Vec3(0, 5, 10);
            Yaw = 0; Pitch = 0.18f;
        }

        public void HandleMouse(float dx, float dy)
        {
            Yaw -= dx * Sensitivity;
            Pitch += -dy * Sensitivity;
            Pitch = Math3D.Clamp(Pitch, -0.52f, 1.16f);
            if (Yaw > Math3D.PI) Yaw -= Math3D.TAU;
            else if (Yaw < -Math3D.PI) Yaw += Math3D.TAU;
        }

        public void Snap(Vec3 focus)
        {
            SmoothTarget = focus + new Vec3(0, HeightOffset, 0);
            float cp = MathF.Cos(Pitch);
            var off = new Vec3(MathF.Sin(Yaw) * cp, MathF.Sin(Pitch), MathF.Cos(Yaw) * cp);
            Position = SmoothTarget + off * Distance;
        }

        public void Update(float dt, Vec3 focus, float speed01 = 0, Func<float, float, float>? heightFn = null, float zoom = 0)
        {
            var aim = focus + new Vec3(0, HeightOffset, 0);
            SmoothTarget = Vec3.Lerp(SmoothTarget, aim, Math.Min(1f, dt * 5f));
            BaseDistance = Math3D.Clamp(BaseDistance + zoom, 2.6f, 13.5f);
            Distance = Math3D.Damp(Distance, BaseDistance + speed01 * 1.15f, 0.02f, dt);
            Fov = Math3D.Damp(Fov, 52f + speed01 * 7.5f, 0.02f, dt);
            float cp = MathF.Cos(Pitch);
            var off = new Vec3(MathF.Sin(Yaw) * cp, MathF.Sin(Pitch), MathF.Cos(Yaw) * cp);
            var pos = SmoothTarget + off * Distance;
            if (heightFn != null)
            {
                float gh = heightFn(pos.X, pos.Z) + 0.85f;
                if (pos.Y < gh) pos = new Vec3(pos.X, gh, pos.Z);
            }
            Position = pos;
        }

        public float[] ViewMatrix() => Math3D.LookAt(Position, SmoothTarget);
        public float[] ProjMatrix(float aspect) => Math3D.Perspective(Fov, aspect, 0.12f, 900f);

        public Vec3 ForwardFlat() => new Vec3(-MathF.Sin(Yaw), 0, -MathF.Cos(Yaw)).Normalized();
    }
}
