// Skinning.cs — GPU 蒙皮骨架 (8 关节 · 线性混合蒙皮)
// 移植自遗留 Python 构建的 skeleton.py / anim.py
using System;
using System.Collections.Generic;

namespace Farwalk.Engine
{
    // 骨骼索引常量 (与 SkinnedMeshGen 共享)
    public static class Bone
    {
        public const int Hips = 0;
        public const int Spine = 1;
        public const int Head = 2;
        public const int ArmL = 3;
        public const int ArmR = 4;
        public const int LegL = 5;
        public const int LegR = 6;
        public const int Tail = 7;
        public const int Count = 8;
    }

    public struct JointPose
    {
        public float Rx, Ry, Rz;     // 局部欧拉旋转
        public float Tx, Ty, Tz;     // 局部附加平移
        public float S;              // 均匀缩放
    }

    public class Skeleton
    {
        public readonly string[] Names = { "hips", "spine", "head", "armL", "armR", "legL", "legR", "tail" };
        public readonly int[] Parent = { -1, 0, 1, 1, 1, 0, 0, 0 };

        // 绑定姿态: 每关节相对父级的偏移 (局部空间)
        public Vec3[] BindLocal = new Vec3[Bone.Count];
        // 绑定姿态世界矩阵的逆
        float[][] _invBind = new float[Bone.Count][];
        // 输出: 8 × mat4 = 128 floats, 直接喂给 uBones[8]
        public float[] SkinMatrices = new float[Bone.Count * 16];

        public JointPose[] Pose = new JointPose[Bone.Count];
        public float Height { get; private set; }

        public Skeleton(float height = 1.74f)
        {
            Height = height;
            float legH = height * 0.44f, torsoH = height * 0.34f, headR = height * 0.078f;

            var bindWorld = new Vec3[Bone.Count];
            bindWorld[Bone.Hips] = new Vec3(0, legH, 0);
            bindWorld[Bone.Spine] = new Vec3(0, legH + torsoH * 0.55f, 0);
            bindWorld[Bone.Head] = new Vec3(0, legH + torsoH + headR * 0.9f, 0);
            bindWorld[Bone.ArmL] = new Vec3(height * 0.135f, legH + torsoH * 0.88f, 0);
            bindWorld[Bone.ArmR] = new Vec3(-height * 0.135f, legH + torsoH * 0.88f, 0);
            bindWorld[Bone.LegL] = new Vec3(height * 0.065f, legH, 0);
            bindWorld[Bone.LegR] = new Vec3(-height * 0.065f, legH, 0);
            // 角色朝向为模型局部 -Z, 故尾部位于 +Z (身后)
            bindWorld[Bone.Tail] = new Vec3(0, legH + height * 0.02f, height * 0.075f);

            for (int i = 0; i < Bone.Count; i++)
            {
                int p = Parent[i];
                BindLocal[i] = p < 0 ? bindWorld[i] : bindWorld[i] - bindWorld[p];
                var bw = Math3D.Mat4Identity();
                bw[12] = bindWorld[i].X; bw[13] = bindWorld[i].Y; bw[14] = bindWorld[i].Z;
                _invBind[i] = Math3D.Invert(bw);
                Pose[i] = new JointPose { S = 1f };
            }
            ResetPose();
            Evaluate();
        }

        public void ResetPose()
        {
            for (int i = 0; i < Bone.Count; i++)
                Pose[i] = new JointPose { S = 1f };
        }

        // 计算最终蒙皮矩阵 (world_i * invBind_i)
        public void Evaluate()
        {
            var world = new float[Bone.Count][];
            for (int i = 0; i < Bone.Count; i++)
            {
                var p = Pose[i];
                var local = Math3D.Compose(
                    BindLocal[i].X + p.Tx, BindLocal[i].Y + p.Ty, BindLocal[i].Z + p.Tz,
                    p.Rx, p.Ry, p.Rz, p.S, p.S, p.S);
                int par = Parent[i];
                world[i] = par < 0 ? local : Math3D.Mul(world[par], local);
            }
            for (int i = 0; i < Bone.Count; i++)
            {
                var skin = Math3D.Mul(world[i], _invBind[i]);
                Array.Copy(skin, 0, SkinMatrices, i * 16, 16);
            }
        }

        // 供调试/相机使用: 关节世界位置 (模型空间)
        public Vec3 JointPosition(int i)
        {
            var m = new float[16];
            Array.Copy(SkinMatrices, i * 16, m, 0, 16);
            // skin * bindWorld = world
            return new Vec3(m[12], m[13], m[14]);
        }
    }

    public enum AnimClip { Idle, Walk, Run, Glide, Air }

    // 过程式动画采样器: 无外部动画资源, 纯函数驱动
    public class AnimController
    {
        public AnimClip Clip = AnimClip.Idle;
        public float Phase;        // 步态相位 (弧度)
        public float Blend;        // 行走强度 0..1
        public float ClipTime;     // 当前片段累计时间
        float _blendTarget;

        public void Update(float dt, bool moving, bool sprinting, bool grounded, bool gliding, float speed01)
        {
            ClipTime += dt;
            AnimClip want;
            if (gliding) want = AnimClip.Glide;
            else if (!grounded) want = AnimClip.Air;
            else if (moving && sprinting) want = AnimClip.Run;
            else if (moving) want = AnimClip.Walk;
            else want = AnimClip.Idle;
            if (want != Clip) { Clip = want; ClipTime = 0f; }

            float rate = Clip switch
            {
                AnimClip.Run => 10.6f,
                AnimClip.Walk => 6.4f,
                _ => 2.0f,
            };
            Phase += dt * rate;
            if (Phase > Math3D.TAU) Phase -= Math3D.TAU;

            _blendTarget = (Clip == AnimClip.Walk || Clip == AnimClip.Run) ? 1f : 0f;
            Blend += (_blendTarget - Blend) * MathF.Min(1f, dt * 9f);
        }

        // 把当前动画写入骨架姿态
        public void Apply(Skeleton sk, float t)
        {
            sk.ResetPose();
            float p = Phase;
            float sn = MathF.Sin(p), cs = MathF.Cos(p);

            // ---- 基础呼吸 (所有片段共有) ----
            float breathe = MathF.Sin(t * 1.35f);
            sk.Pose[Bone.Spine].Rx = breathe * 0.022f;
            sk.Pose[Bone.Head].Ry = MathF.Sin(t * 0.47f) * 0.11f;
            sk.Pose[Bone.Head].Rx = MathF.Sin(t * 0.31f) * 0.05f;
            sk.Pose[Bone.Tail].Ry = MathF.Sin(t * 1.9f) * 0.20f;
            sk.Pose[Bone.Tail].Rx = 0.22f + MathF.Sin(t * 1.4f) * 0.10f;

            switch (Clip)
            {
                case AnimClip.Idle:
                    sk.Pose[Bone.ArmL].Rz = -0.06f + breathe * 0.03f;
                    sk.Pose[Bone.ArmR].Rz = 0.06f - breathe * 0.03f;
                    sk.Pose[Bone.Hips].Ty = breathe * 0.012f;
                    break;

                case AnimClip.Walk:
                case AnimClip.Run:
                    {
                        bool run = Clip == AnimClip.Run;
                        float legAmp = run ? 0.86f : 0.54f;
                        float armAmp = run ? 0.72f : 0.40f;
                        float lean = run ? -0.26f : -0.09f;

                        sk.Pose[Bone.LegL].Rx = sn * legAmp * Blend;
                        sk.Pose[Bone.LegR].Rx = -sn * legAmp * Blend;
                        // 摆动腿轻微外张
                        sk.Pose[Bone.LegL].Rz = MathF.Max(sn, 0f) * 0.06f * Blend;
                        sk.Pose[Bone.LegR].Rz = -MathF.Max(-sn, 0f) * 0.06f * Blend;

                        sk.Pose[Bone.ArmL].Rx = -sn * armAmp * Blend;
                        sk.Pose[Bone.ArmR].Rx = sn * armAmp * Blend;
                        sk.Pose[Bone.ArmL].Rz = -0.09f - (run ? 0.10f : 0.0f);
                        sk.Pose[Bone.ArmR].Rz = 0.09f + (run ? 0.10f : 0.0f);

                        sk.Pose[Bone.Spine].Rx += lean * Blend;
                        sk.Pose[Bone.Spine].Ry = -sn * 0.09f * Blend;
                        sk.Pose[Bone.Hips].Ry = sn * 0.11f * Blend;
                        sk.Pose[Bone.Hips].Rz = cs * 0.035f * Blend;
                        // 竖直起伏 (每步两次)
                        sk.Pose[Bone.Hips].Ty = MathF.Abs(sn) * (run ? 0.075f : 0.036f) * Blend;
                        sk.Pose[Bone.Head].Rx += -lean * 0.55f * Blend;
                        sk.Pose[Bone.Tail].Rx = 0.30f + sn * 0.16f;
                        break;
                    }

                case AnimClip.Glide:
                    {
                        float flap = MathF.Sin(t * 2.6f) * 0.08f;
                        sk.Pose[Bone.ArmL].Rz = -1.28f + flap;
                        sk.Pose[Bone.ArmR].Rz = 1.28f - flap;
                        sk.Pose[Bone.ArmL].Rx = -0.20f;
                        sk.Pose[Bone.ArmR].Rx = -0.20f;
                        sk.Pose[Bone.Spine].Rx += -0.38f;
                        sk.Pose[Bone.LegL].Rx = -0.30f + flap * 0.5f;
                        sk.Pose[Bone.LegR].Rx = -0.30f - flap * 0.5f;
                        sk.Pose[Bone.LegL].Rz = 0.14f;
                        sk.Pose[Bone.LegR].Rz = -0.14f;
                        sk.Pose[Bone.Tail].Rx = 0.62f;
                        sk.Pose[Bone.Head].Rx += 0.24f;
                        break;
                    }

                case AnimClip.Air:
                    {
                        float k = Math3D.Clamp(ClipTime * 4f, 0f, 1f);
                        sk.Pose[Bone.LegL].Rx = 0.55f * k;
                        sk.Pose[Bone.LegR].Rx = 0.22f * k;
                        sk.Pose[Bone.ArmL].Rz = -0.52f * k;
                        sk.Pose[Bone.ArmR].Rz = 0.52f * k;
                        sk.Pose[Bone.ArmL].Rx = -0.42f * k;
                        sk.Pose[Bone.ArmR].Rx = -0.42f * k;
                        sk.Pose[Bone.Spine].Rx += -0.12f * k;
                        sk.Pose[Bone.Tail].Rx = 0.48f;
                        break;
                    }
            }
            sk.Evaluate();
        }
    }
}
