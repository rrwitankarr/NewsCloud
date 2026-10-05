"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getAuthToken, API_BASE_URL } from "@/lib/api";
import Link from "next/link";
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  Search,
  ExternalLink,
} from "lucide-react";
import { motion } from "framer-motion";

type VerificationStatus = "idle" | "processing" | "complete" | "error";

interface Evidence {
  text?: string;
}

interface Result {
  verdict: string | null;
  explanation: string;
  evidence: Evidence[] | string[];
  urls: string[];

  verification_status?: "normal" | "degraded";
  ai_available?: boolean;
  degradation_reason?: string;
  message?: string;
}

export default function Home() {
  const { user } = useAuth();

  const [claim, setClaim] = useState("");
  const [status, setStatus] =
    useState<VerificationStatus>("idle");
  const [messages, setMessages] = useState<string[]>([]);
  const [result, setResult] = useState<Result | null>(null);

  const verifyClaim = async () => {
    if (!claim.trim()) return;

    setStatus("processing");
    setMessages(["Starting verification..."]);
    setResult(null);

    const token = getAuthToken();

    try {
      const response = await fetch(
        `${API_BASE_URL}/claims/verify/stream`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            content: claim,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(
          "Failed to start verification. Please try again."
        );
      }

      if (!response.body) {
        throw new Error(
          "ReadableStream not supported in this browser."
        );
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");

      let done = false;

      while (!done) {
        const {
          value,
          done: readerDone,
        } = await reader.read();

        done = readerDone;

        if (value) {
          const chunk = decoder.decode(value, {
            stream: true,
          });

          const lines = chunk.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const dataStr = line.substring(6);

              try {
                const data = JSON.parse(dataStr);

                if (data.status === "processing") {
                  setMessages((prev) => [
                    ...prev,
                    data.message,
                  ]);
                } else if (
                  data.status === "complete"
                ) {
                  setResult(data as Result);
                  setStatus("complete");
                  return;
                } else if (
                  data.status === "error"
                ) {
                  setMessages((prev) => [
                    ...prev,
                    `Error: ${data.message}`,
                  ]);

                  setStatus("error");
                  return;
                }
              } catch (err) {
                console.error(
                  "Failed to parse SSE data",
                  dataStr
                );
              }
            }
          }
        }
      }

      setStatus("error");

      setMessages((prev) => [
        ...prev,
        "Connection closed unexpectedly.",
      ]);
    } catch (err: any) {
      console.error(err);

      setStatus("error");

      setMessages((prev) => [
        ...prev,
        err.message ||
          "An unknown error occurred.",
      ]);
    }
  };

  const handleSubmit = async (
    e: React.FormEvent
  ) => {
    e.preventDefault();
    await verifyClaim();
  };

  if (!user) {
    return (
      <div className="text-center py-20">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          Verify the News with AVeriTeC
        </h1>

        <p className="text-lg text-gray-600 mb-8">
          Please log in to submit a claim and verify news.
        </p>

        <Link
          href="/login"
          className="bg-blue-600 text-white font-medium py-3 px-6 rounded-md hover:bg-blue-700"
        >
          Log In
        </Link>
      </div>
    );
  }

  const getVerdictColor = (
    verdict: string
  ) => {
    switch (verdict?.toUpperCase()) {
      case "TRUE":
        return "text-green-600 bg-green-50 border-green-200";

      case "FALSE":
        return "text-red-600 bg-red-50 border-red-200";

      case "MISLEADING":
        return "text-orange-600 bg-orange-50 border-orange-200";

      default:
        return "text-gray-600 bg-gray-50 border-gray-200";
    }
  };

  const getVerdictIcon = (
    verdict: string
  ) => {
    switch (verdict?.toUpperCase()) {
      case "TRUE":
        return (
          <CheckCircle
            className="text-green-600"
            size={32}
          />
        );

      case "FALSE":
        return (
          <XCircle
            className="text-red-600"
            size={32}
          />
        );

      case "MISLEADING":
        return (
          <AlertTriangle
            className="text-orange-600"
            size={32}
          />
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-8">

      {/* ================================================== */}
      {/* INPUT SECTION */}
      {/* ================================================== */}

      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">

        <h2 className="text-xl font-bold text-gray-900 mb-4">
          Verify a Claim
        </h2>

        <form onSubmit={handleSubmit}>

          <motion.textarea
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            value={claim}
            onChange={(e) =>
              setClaim(e.target.value)
            }
            disabled={
              status === "processing"
            }
            placeholder="Paste a news headline, tweet, or claim here to verify its authenticity..."
            className="w-full h-32 p-4 border border-gray-300 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-4 disabled:opacity-50 text-gray-900 bg-white shadow-sm"
          />

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            type="submit"
            disabled={
              status === "processing" ||
              !claim.trim()
            }
            className="flex items-center gap-2 bg-indigo-600 text-white font-medium py-2 px-6 rounded-md hover:bg-indigo-700 disabled:opacity-50 shadow-md transition-colors"
          >
            <Search size={18} />

            {status === "processing"
              ? "Verifying..."
              : "Verify Claim"}
          </motion.button>

        </form>
      </div>

      {/* ================================================== */}
      {/* LOADING STATES */}
      {/* ================================================== */}

      {status === "processing" && (
        <motion.div
          initial={{
            opacity: 0,
            y: 20,
          }}
          animate={{
            opacity: 1,
            y: 0,
          }}
          className="bg-indigo-50 border border-indigo-100 rounded-xl p-6 shadow-sm"
        >

          <h3 className="font-semibold text-indigo-900 mb-4 flex items-center gap-2">

            <div className="animate-spin h-4 w-4 border-2 border-indigo-600 border-t-transparent rounded-full" />

            Processing Pipeline

          </h3>

          <ul className="space-y-2 text-sm text-indigo-800 font-mono bg-indigo-100/50 p-4 rounded border border-indigo-200">

            {messages.map(
              (msg, idx) => (
                <motion.li
                  initial={{
                    opacity: 0,
                    x: -10,
                  }}
                  animate={{
                    opacity: 1,
                    x: 0,
                  }}
                  key={idx}
                  className="flex gap-2"
                >

                  <span className="text-indigo-400">
                    [
                    {new Date().toLocaleTimeString()}
                    ]
                  </span>

                  {msg}

                </motion.li>
              )
            )}

          </ul>

        </motion.div>
      )}

      {/* ================================================== */}
      {/* ERROR STATE */}
      {/* ================================================== */}

      {status === "error" && (
        <motion.div
          initial={{
            opacity: 0,
            y: 20,
          }}
          animate={{
            opacity: 1,
            y: 0,
          }}
          className="bg-red-50 border border-red-200 p-6 rounded-xl text-red-700 shadow-sm"
        >

          <h3 className="font-bold flex items-center gap-2 mb-2">
            <XCircle size={20} />
            Error verifying claim
          </h3>

          <p>
            {messages[messages.length - 1]}
          </p>

        </motion.div>
      )}

      {/* ================================================== */}
      {/* RESULTS VIEW */}
      {/* ================================================== */}

      {status === "complete" &&
        result && (

          <motion.div
            initial={{
              opacity: 0,
              y: 30,
            }}
            animate={{
              opacity: 1,
              y: 0,
            }}
            transition={{
              duration: 0.5,
            }}
            className="space-y-6"
          >

            {/* ================================================== */}
            {/* VERDICT */}
            {/* ================================================== */}

            {result.verification_status ===
            "degraded" ? (

              <motion.div
                initial={{
                  opacity: 0,
                  y: 20,
                }}
                animate={{
                  opacity: 1,
                  y: 0,
                }}
                className="p-6 rounded-xl border border-amber-200 bg-amber-50 shadow-sm"
              >

                <div className="flex flex-col md:flex-row items-start gap-5">

                  <div className="flex-shrink-0 flex items-center justify-center bg-white p-4 rounded-full shadow-md">

                    <AlertTriangle
                      className="text-amber-500"
                      size={32}
                    />

                  </div>

                  <div className="flex-1">

                    <h2 className="text-2xl font-bold text-amber-900 mb-2">
                      Verification Temporarily Degraded
                    </h2>

                    <p className="text-amber-800 leading-relaxed mb-4">
                      AI verification is temporarily unavailable.
                      NewsCloud successfully collected supporting
                      evidence, but a complete AI-generated verdict
                      could not be produced.
                    </p>

                    <div className="flex flex-wrap gap-2 mb-5">

                      <span className="inline-flex items-center px-3 py-1 rounded-full bg-white border border-amber-200 text-sm text-amber-800">
                        ⚠ AI verification unavailable
                      </span>

                      <span className="inline-flex items-center px-3 py-1 rounded-full bg-white border border-green-200 text-sm text-green-700">
                        ✓ Evidence collected
                      </span>

                    </div>

                    <div className="bg-white/70 border border-amber-200 rounded-lg p-4 mb-5">

                      <p className="text-sm font-semibold text-gray-700">
                        Verification mode
                      </p>

                      <p className="text-sm text-gray-600 mt-1">
                        Evidence collection completed. AI verdict
                        temporarily unavailable.
                      </p>

                    </div>

                    <button
                      type="button"
                      onClick={verifyClaim}
                      disabled={
                        status === "processing"
                      }
                      className="bg-indigo-600 text-white px-5 py-2.5 rounded-lg hover:bg-indigo-700 disabled:opacity-50 font-medium shadow-md transition-colors"
                    >
                      {status === "processing"
                        ? "Retrying..."
                        : "Try Again"}
                    </button>

                  </div>

                </div>

              </motion.div>

            ) : (

              <div
                className={`p-6 rounded-xl border flex flex-col md:flex-row items-center gap-6 shadow-sm ${getVerdictColor(
                  result.verdict || ""
                )}`}
              >

                <motion.div
                  initial={{
                    scale: 0,
                  }}
                  animate={{
                    scale: 1,
                  }}
                  transition={{
                    type: "spring",
                    stiffness: 200,
                    delay: 0.2,
                  }}
                  className="flex-shrink-0 flex flex-col items-center justify-center bg-white p-4 rounded-full shadow-md"
                >
                  {getVerdictIcon(
                    result.verdict || ""
                  )}
                </motion.div>

                <div>

                  <h2 className="text-2xl font-bold mb-2">
                    Verdict:{" "}
                    {(
                      result.verdict ||
                      "UNVERIFIABLE"
                    ).toUpperCase()}
                  </h2>

                  <p className="opacity-90 leading-relaxed">
                    {result.explanation}
                  </p>

                </div>

              </div>
            )}

            {/* ================================================== */}
            {/* SUPPORTING EVIDENCE */}
            {/* ================================================== */}

            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">

              <h3 className="text-lg font-bold text-gray-900 mb-4 border-b pb-2">
                Supporting Evidence
              </h3>

              <div className="space-y-4">

                {result.evidence &&
                result.evidence.length > 0 ? (

                  result.evidence.map(
                    (chunk, idx) => (

                      <motion.div
                        initial={{
                          opacity: 0,
                          y: 10,
                        }}
                        animate={{
                          opacity: 1,
                          y: 0,
                        }}
                        transition={{
                          delay: 0.1 * idx,
                        }}
                        key={idx}
                        className="bg-gray-50 p-4 rounded-lg border border-gray-100 text-sm text-gray-700 leading-relaxed shadow-sm"
                      >
                        "
                        {typeof chunk ===
                        "string"
                          ? chunk
                          : chunk.text ||
                            JSON.stringify(
                              chunk
                            )}
                        "
                      </motion.div>

                    )
                  )

                ) : (

                  <p className="text-gray-500 italic">
                    No specific text evidence returned.
                  </p>

                )}

              </div>

              {result.urls &&
                result.urls.length > 0 && (

                  <div className="mt-6 pt-4 border-t border-gray-100">

                    <h4 className="font-semibold text-gray-700 mb-3">
                      Sources Searched:
                    </h4>

                    <ul className="flex flex-col gap-2">

                      {result.urls.map(
                        (url, idx) => (

                          <li key={idx}>

                            {url.startsWith(
                              "http"
                            ) ? (

                              <a
                                href={url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-indigo-600 hover:text-indigo-800 hover:underline flex items-center gap-1 text-sm transition-colors"
                              >

                                <ExternalLink
                                  size={14}
                                />

                                {url}

                              </a>

                            ) : (

                              <span className="text-gray-600 flex items-center gap-1 text-sm bg-gray-100 px-2 py-1 rounded w-fit">
                                {url}
                              </span>

                            )}

                          </li>

                        )
                      )}

                    </ul>

                  </div>

                )}

            </div>

            {/* ================================================== */}
            {/* COMPLAINT FLOW */}
            {/* ================================================== */}

            {result.verdict &&
              (
                result.verdict.toUpperCase() ===
                  "FALSE" ||
                result.verdict.toUpperCase() ===
                  "MISLEADING"
              ) && (

                <motion.div
                  whileHover={{
                    scale: 1.01,
                  }}
                  className="bg-gradient-to-r from-indigo-50 to-blue-50 p-6 rounded-xl border border-indigo-100 flex justify-between items-center shadow-sm"
                >

                  <div>

                    <h3 className="font-bold text-indigo-900 text-lg">
                      Found this on a news site?
                    </h3>

                    <p className="text-sm text-indigo-700 mt-1">
                      Help combat misinformation by filing a complaint.
                      A successful, new complaint earns 1 GEM.
                    </p>

                  </div>

                  <Link
                    href={`/complaint?claim=${encodeURIComponent(
                      claim
                    )}`}
                    className="bg-indigo-600 text-white px-5 py-2.5 rounded-lg hover:bg-indigo-700 font-medium shadow-md transition-all hover:shadow-lg whitespace-nowrap"
                  >
                    File Complaint
                  </Link>

                </motion.div>

              )}

          </motion.div>

        )}

    </div>
  );
}