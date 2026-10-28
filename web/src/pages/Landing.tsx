import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export function Landing() {
  const [service, setService] = useState<"checking" | "online" | "offline">("checking");

  useEffect(() => {
    let active = true;
    api
      .health()
      .then(() => active && setService("online"))
      .catch(() => active && setService("offline"));
    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="mx-auto w-full max-w-[1200px] px-5 py-20">
      <p className="eyebrow">black-box fairness audit</p>
      <h1 className="mt-3 max-w-2xl text-4xl font-semibold tracking-[-0.03em]">
        Watch a model make the same decision twice — with one thing changed.
      </h1>
      <p className="mt-4 max-w-xl text-sm leading-relaxed text-muted">
        FairLens sends twin applicants through a lender model and shows what
        changes when only gender, name, or region differs.
      </p>
      <p className="mt-8 font-mono text-[11px] text-muted">
        audit service:{" "}
        <span className={service === "online" ? "text-ok" : "text-warn"}>
          {service}
        </span>
      </p>
    </section>
  );
}
