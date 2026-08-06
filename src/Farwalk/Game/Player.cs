// Player.cs — 玩家控制器
using System;
using Farwalk.Engine;

namespace Farwalk.Game
{
    public class Player
    {
        public Vec3 Pos, Vel;
        public float Yaw;
        public float Hp = 100, Stamina = 100;
        public float Speed = 5.2f, RunSpeed = 8.5f;
        public bool Gliding, Sprinting, Moving, Climbing, Swimming;
        public float Squash = 1f, Lean = 0f;
        public bool EchoUnlocked;

        public Player(Vec3 spawn)
        {
            Pos = spawn; Vel = new Vec3(0, 0, 0);
        }

        public void Update(float dt, float heightAt, Func<Vec3, Vec3>? gravity = null)
        {
            // 重力
            Vel = new Vec3(Vel.X, Vel.Y - 9.8f * dt * 2.2f, Vel.Z);
            var np = Pos + Vel * dt;
            // 地面碰撞
            float h = heightAt;
            if (np.Y < h)
            {
                np = new Vec3(np.X, h, np.Z);
                Vel = new Vec3(Vel.X, 0, Vel.Z);
            }
            Pos = np;
        }

        public void ApplyMove(float dt, Vec3 wishDir, bool sprint, bool jump, bool jumpHeld)
        {
            float sp = sprint ? RunSpeed : Speed;
            var mv = wishDir * sp;
            Pos = new Vec3(Pos.X + mv.X * dt, Pos.Y, Pos.Z + mv.Z * dt);
            Moving = wishDir.Length() > 0.1f;
            Sprinting = sprint && Moving;
            // 跳跃
            if (jump)
            {
                Vel = new Vec3(Vel.X, 7.0f, Vel.Z);
                Gliding = jumpHeld && Vel.Y < 0;
            }
        }
    }
}
