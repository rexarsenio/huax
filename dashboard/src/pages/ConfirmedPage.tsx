import { useRef } from "react";
import { motion, useScroll } from "motion/react";

import { OilTankerParallax } from "../components/landing/OilTankerParallax";
import huaxLogo from "../assets/landing/huaxlogo.png";

export const ConfirmedPage = () => {
  const containerRef = useRef<HTMLDivElement>(null);

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"],
  });

  return (
    <div ref={containerRef} className="relative min-h-screen bg-white text-gray-900">
      <OilTankerParallax scrollYProgress={scrollYProgress} />

      <section className="relative flex min-h-[75vh] items-center justify-center px-5 pb-16 md:h-screen md:px-6 md:pb-0">
        <motion.div
          className="z-10 mx-auto max-w-4xl space-y-8 text-center"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3 }}
        >
          <div className="relative mt-24 sm:mt-32 md:mt-48 lg:mt-56">
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5, duration: 1 }}
            >
              <motion.img
                src={huaxLogo}
                alt="HUAX Logo"
                className="mx-auto mb-6 w-32 sm:w-36 md:mb-7 md:w-48"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.8, ease: "easeOut" }}
              />
              <div className="group relative mx-auto w-fit">
                <div className="pointer-events-none absolute inset-0 rounded-[32px] border border-white/50 bg-white/30 opacity-0 blur-[22px] transition-opacity duration-500 group-hover:opacity-100" />
                <div className="pointer-events-none absolute inset-0 rounded-[32px] bg-white/10 opacity-0 backdrop-blur-xl transition-opacity duration-500 group-hover:opacity-100" />
                <div className="relative z-10 px-6 py-4 sm:px-8 sm:py-6">
                  <h1 className="text-3xl font-semibold tracking-tight text-[#0b1d3a] sm:text-4xl md:text-5xl">
                    Success! You&rsquo;re on the list.
                  </h1>
                </div>
              </div>
              <div className="group relative mx-auto mt-5 max-w-2xl">
                <div className="pointer-events-none absolute inset-0 rounded-[32px] border border-white/50 bg-white/30 opacity-0 blur-[24px] transition-opacity duration-500 group-hover:opacity-100" />
                <div className="pointer-events-none absolute inset-0 rounded-[32px] bg-white/12 opacity-0 backdrop-blur-xl transition-opacity duration-500 group-hover:opacity-100" />
                <p className="relative z-10 px-5 py-4 text-base leading-relaxed text-[#10254d] sm:px-6 sm:py-5">
                  Thanks for confirming your spot on the HUAX waitlist. We&rsquo;ll be in touch soon with exclusive{" "}
                  <span className="font-semibold text-[#0b1d3a]">&ldquo;Founding Partner&rdquo;</span>{" "}
                  updates and launch details.
                </p>
              </div>
            </motion.div>
          </div>
        </motion.div>
      </section>

      <div className="h-[35vh] md:h-[80vh]" />

      <footer className="relative z-30 border-t border-gray-100 bg-gray-50 py-8">
        <div className="mx-auto max-w-5xl px-6">
          <div className="mb-6 text-center text-xs text-gray-500">
            <p>HUAX is a product of Lazzaro One UG</p>
          </div>

          <div className="mx-auto grid max-w-3xl grid-cols-2 gap-x-6 gap-y-4 text-xs text-gray-500 md:grid-cols-3">
            <div>
              <p>Lazzaro One UG (haftungsbeschränkt)</p>
              <p>Forckenbeckstraße 63c</p>
              <p>14199 Berlin, Germany</p>
            </div>
            <div>
              <p>Managing Director:</p>
              <p>Arsenio Longo</p>
            </div>
            <div>
              <p>Phone: +49 (0)30 24618457</p>
              <p>Email: office@lazzaro.one</p>
            </div>
            <div>
              <p>Commercial Register:</p>
              <p>Amtsgericht Charlottenburg</p>
              <p>HRB 264590 B</p>
            </div>
            <div>
              <p>VAT ID:</p>
              <p>DE368386682</p>
            </div>
            <div>
              <p>Responsible for content (§ 55 RStV):</p>
              <p>Arsenio Longo</p>
            </div>
          </div>

          <div className="mt-6 border-t border-gray-200 pt-6 text-center text-xs text-gray-400">
            <p>&copy; {new Date().getFullYear()} HUAX. Energy Intelligence.</p>
            <p className="mt-2">
              <a className="text-[#0b1d3a] underline underline-offset-4" href="/datenschutz">
                Datenschutzerklärung
              </a>
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
};
