"use client";

import { useEffect, useState } from "react";
import {
  Trophy,
  Gem,
  RefreshCw,
} from "lucide-react";
import { motion } from "framer-motion";

import { API_BASE_URL } from "@/lib/api";

interface LeaderboardUser {
  rank: number;
  username: string;
  gems: number;
}

interface LeaderboardResponse {
  leaderboard: LeaderboardUser[];
}

export default function LeaderboardPage() {
  const [users, setUsers] = useState<
    LeaderboardUser[]
  >([]);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  const fetchLeaderboard = async () => {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        `${API_BASE_URL}/leaderboard`,
        {
          method: "GET",
          cache: "no-store",
        }
      );

      if (!response.ok) {
        throw new Error(
          "Failed to load leaderboard."
        );
      }

      const data: LeaderboardResponse =
        await response.json();

      setUsers(
        data.leaderboard || []
      );

    } catch (err) {
      console.error(
        "Leaderboard error:",
        err
      );

      setError(
        err instanceof Error
          ? err.message
          : "Failed to load leaderboard."
      );

    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLeaderboard();
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-10">

      <div className="max-w-4xl mx-auto">

        {/* ================================================== */}
        {/* HEADER */}
        {/* ================================================== */}

        <motion.div
          initial={{
            opacity: 0,
            y: -20,
          }}
          animate={{
            opacity: 1,
            y: 0,
          }}
          className="text-center mb-10"
        >

          <div className="flex justify-center items-center gap-3 mb-3">

            <Trophy
              size={42}
              className="text-amber-500"
            />

            <h1 className="text-4xl font-bold text-gray-900">
              Global Leaderboard
            </h1>

          </div>

          <p className="text-gray-600 text-lg">
            Top contributors combating misinformation
          </p>

        </motion.div>

        {/* ================================================== */}
        {/* REFRESH BUTTON */}
        {/* ================================================== */}

        <div className="flex justify-end mb-4">

          <button
            type="button"
            onClick={fetchLeaderboard}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 shadow-sm"
          >

            <RefreshCw
              size={16}
              className={
                loading
                  ? "animate-spin"
                  : ""
              }
            />

            Refresh

          </button>

        </div>

        {/* ================================================== */}
        {/* ERROR */}
        {/* ================================================== */}

        {error && (
          <div className="mb-6 p-4 rounded-lg border border-red-200 bg-red-50 text-red-700">
            {error}
          </div>
        )}

        {/* ================================================== */}
        {/* LEADERBOARD */}
        {/* ================================================== */}

        <motion.div
          initial={{
            opacity: 0,
            y: 20,
          }}
          animate={{
            opacity: 1,
            y: 0,
          }}
          className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden"
        >

          {/* Table Header */}

          <div className="grid grid-cols-[120px_1fr_180px] px-6 py-5 border-b border-gray-200 text-gray-700 font-semibold">

            <div>
              Rank
            </div>

            <div>
              User
            </div>

            <div className="text-right">
              GEMs Earned
            </div>

          </div>

          {/* ================================================== */}
          {/* LOADING */}
          {/* ================================================== */}

          {loading && (
            <div className="py-16 text-center text-gray-500">

              <RefreshCw
                size={28}
                className="animate-spin mx-auto mb-3"
              />

              Loading leaderboard...

            </div>
          )}

          {/* ================================================== */}
          {/* EMPTY */}
          {/* ================================================== */}

          {!loading &&
            !error &&
            users.length === 0 && (

              <div className="py-16 text-center text-gray-500">
                No users found.
              </div>

            )}

          {/* ================================================== */}
          {/* USERS */}
          {/* ================================================== */}

          {!loading &&
            users.map(
              (user, index) => (

                <motion.div
                  key={user.username}
                  initial={{
                    opacity: 0,
                    x: -10,
                  }}
                  animate={{
                    opacity: 1,
                    x: 0,
                  }}
                  transition={{
                    delay:
                      index * 0.05,
                  }}
                  className="grid grid-cols-[120px_1fr_180px] items-center px-6 py-5 border-b border-gray-100 last:border-b-0 hover:bg-gray-50"
                >

                  {/* Rank */}

                  <div>

                    {user.rank === 1 ? (

                      <div className="w-9 h-9 rounded-full bg-yellow-100 flex items-center justify-center font-bold text-yellow-700">
                        1
                      </div>

                    ) : user.rank === 2 ? (

                      <div className="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center font-bold text-gray-700">
                        2
                      </div>

                    ) : user.rank === 3 ? (

                      <div className="w-9 h-9 rounded-full bg-orange-100 flex items-center justify-center font-bold text-orange-700">
                        3
                      </div>

                    ) : (

                      <div className="text-gray-500 font-medium pl-3">
                        {user.rank}
                      </div>

                    )}

                  </div>

                  {/* Username */}

                  <div className="font-medium text-gray-900">
                    {user.username}
                  </div>

                  {/* GEMs */}

                  <div className="flex justify-end">

                    <div className="flex items-center gap-2 bg-indigo-50 text-indigo-600 font-bold px-4 py-2 rounded-full">

                      <Gem size={17} />

                      <span>
                        {user.gems}
                      </span>

                    </div>

                  </div>

                </motion.div>

              )
            )}

        </motion.div>

      </div>

    </div>
  );
}