import { motion, useTransform, type MotionValue } from "motion/react";

import tankerImage from "../../assets/landing/shipimage.png";

interface OilTankerParallaxProps {
  scrollYProgress: MotionValue<number>;
}

export const OilTankerParallax = ({ scrollYProgress }: OilTankerParallaxProps) => {
  const isClient = typeof window !== "undefined";
  const isMobile = isClient && window.innerWidth < 768;

  const yRange = isMobile ? ["22vh", "68vh"] : ["-5vh", "85vh"];
  const scaleRange = isMobile ? [0.95, 1.05, 1.15, 1.25, 1.35, 1.45, 1.55] : [1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2];
  const xRange = isMobile ? ["82%", "45%"] : ["70%", "25%"];

  const y = useTransform(scrollYProgress, [0, 1], yRange);
  const scale = useTransform(
    scrollYProgress,
    [0, 0.17, 0.33, 0.5, 0.67, 0.83, 1],
    scaleRange,
  );
  const rotate = useTransform(scrollYProgress, [0, 1], [-3, 2]);
  const x = useTransform(scrollYProgress, [0, 1], xRange);

  return (
    <motion.div
      className="pointer-events-none fixed top-0 z-0"
      style={{
        y,
        left: x,
        x: "-50%",
        rotate,
        scale,
      }}
    >
      <motion.img
        src={tankerImage}
        alt="Oil tanker silhouette"
        className="w-[320px] sm:w-[420px] md:w-[600px] lg:w-[800px]"
        style={{ filter: "drop-shadow(0 20px 40px rgba(0, 0, 0, 0.4))" }}
        animate={{ y: [0, -8, 0] }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
      />
    </motion.div>
  );
};
