import Link from "next/link";
import { useTranslations } from "next-intl";

export default function Home() {
  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section
        className="text-white py-20 px-8"
        style={{ background: "linear-gradient(135deg, #003366 0%, #006699 100%)" }}
      >
        <div className="max-w-5xl mx-auto">
          <div className="text-xs font-bold tracking-widest uppercase opacity-70 mb-3">
            International Seabed Authority
          </div>
          <h1 className="text-4xl font-bold mb-4 leading-tight">
            Draft Exploitation Regulations
            <br />
            <span className="text-yellow-300">Polymetallic Nodules</span>
          </h1>
          <p className="text-lg opacity-80 max-w-2xl mb-6">
            Open platform for stakeholder engagement in the development of
            exploitation regulations for mineral resources in the Area.
          </p>
          <div className="flex flex-wrap gap-3 mb-8">
            <span className="bg-white bg-opacity-20 px-4 py-1.5 rounded-full text-sm font-semibold animate-pulse">
              ★ Current Text: ISBA/31/C/CRP.1/Rev.2
            </span>
            <span className="bg-white bg-opacity-15 px-4 py-1.5 rounded-full text-sm">
              Session 31 · March 2026
            </span>
            <span className="bg-white bg-opacity-15 px-4 py-1.5 rounded-full text-sm">
              Phase: Finalisation Negotiations
            </span>
          </div>
          <div className="flex flex-wrap gap-4">
            <Link
              href="/timeline"
              className="bg-yellow-400 text-blue-900 font-bold px-6 py-3 rounded-xl hover:bg-yellow-300 transition-colors"
            >
              📅 View Document Timeline
            </Link>
            <Link
              href="/regulations"
              className="bg-white text-blue-900 font-bold px-6 py-3 rounded-xl hover:bg-blue-50 transition-colors"
            >
              📖 Read the Regulations
            </Link>
            <Link
              href="/chat"
              className="border border-white text-white font-bold px-6 py-3 rounded-xl hover:bg-white hover:text-blue-900 transition-colors"
            >
              💬 Ask a Question
            </Link>
          </div>
        </div>
      </section>

      {/* Status Dashboard */}
      <section className="max-w-5xl mx-auto px-8 py-12">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">
          Regulation Status Dashboard
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
          <StatusCard icon="📄" label="Current Document" value="ISBA/31/C/CRP.1/Rev.2" sub="Feb 2026" color="blue" />
          <StatusCard icon="⚠️" label="Outstanding Issues" value="See CRP.4" sub="Indicative list" color="yellow" />
          <StatusCard icon="🔄" label="Suspense Provisions" value="See CRP.3" sub="Further Revised" color="orange" />
          <StatusCard icon="🏛️" label="Current Session" value="ISBA/31" sub="9–19 Mar 2026 (Part I)" color="green" />
        </div>

        {/* Progression Timeline mini */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold text-gray-800">Regulatory Text Progression</h3>
            <Link href="/timeline" className="text-sm text-blue-600 hover:underline">
              Full timeline →
            </Link>
          </div>
          <div className="flex items-center gap-2 overflow-x-auto pb-2">
            {PROGRESSION.map((step, i) => (
              <div key={step.ref} className="flex items-center gap-2 shrink-0">
                <div
                  className={`rounded-lg px-3 py-2 text-xs font-semibold border ${
                    step.current
                      ? "bg-blue-900 text-white border-blue-900 ring-2 ring-yellow-400"
                      : "bg-gray-50 text-gray-600 border-gray-200"
                  }`}
                >
                  <div>{step.ref}</div>
                  <div className="opacity-70 font-normal">{step.date}</div>
                </div>
                {i < PROGRESSION.length - 1 && (
                  <div className="text-gray-300 font-bold">→</div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Quick actions */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <QuickAction
            href="/regulations"
            icon="📖"
            title="Read the Text"
            desc="Browse regulations by Part, with bracket and alternative highlighting"
          />
          <QuickAction
            href="/chat"
            icon="💬"
            title="Ask a Question"
            desc="Grounded answers from the regulatory text — no hallucination, fully cited"
          />
          <QuickAction
            href="/timeline"
            icon="📅"
            title="Document History"
            desc="Full timeline from 2014 discussion papers to the current text"
          />
        </div>
      </section>
    </div>
  );
}

function StatusCard({
  icon, label, value, sub, color,
}: {
  icon: string; label: string; value: string; sub: string; color: string;
}) {
  const colors: Record<string, string> = {
    blue: "border-blue-200 bg-blue-50",
    yellow: "border-yellow-200 bg-yellow-50",
    orange: "border-orange-200 bg-orange-50",
    green: "border-green-200 bg-green-50",
  };
  return (
    <div className={`rounded-xl border p-4 ${colors[color] || colors.blue}`}>
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className="font-bold text-sm text-gray-900">{value}</div>
      <div className="text-xs text-gray-500">{sub}</div>
    </div>
  );
}

function QuickAction({
  href, icon, title, desc,
}: {
  href: string; icon: string; title: string; desc: string;
}) {
  return (
    <Link
      href={href}
      className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 hover:shadow-md hover:-translate-y-0.5 transition-all flex gap-4"
    >
      <div className="text-3xl shrink-0">{icon}</div>
      <div>
        <div className="font-bold text-gray-900 mb-1">{title}</div>
        <div className="text-sm text-gray-500">{desc}</div>
      </div>
    </Link>
  );
}

const PROGRESSION = [
  { ref: "Working Draft", date: "2016", current: false },
  { ref: "ISBA/23/LTC", date: "2017", current: false },
  { ref: "ISBA/24/LTC", date: "2018", current: false },
  { ref: "ISBA/25/C/WP.1", date: "2019", current: false },
  { ref: "ISBA/29/C/CRP.1", date: "Feb 2024", current: false },
  { ref: "ISBA/30/C/CRP.1", date: "Nov 2024", current: false },
  { ref: "ISBA/31/C/CRP.1/Rev.2", date: "Feb 2026 ★", current: true },
];
