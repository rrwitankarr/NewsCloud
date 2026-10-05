"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import { Gem, LogOut, User as UserIcon } from "lucide-react";
import { motion } from "framer-motion";
import FactCheckerBadge from "@/components/FactCheckerBadge";
import { getAuthToken, API_BASE_URL } from "@/lib/api";

type Badge = {
  badge_number: number;
  award_month: number;
  award_year: number;
  title: string;
};

export default function Navbar() {
  const { user, logout } = useAuth();

  const [badges, setBadges] = useState<Badge[]>([]);

  // ============================================================
  // LOAD USER'S FACT CHECKER BADGES
  // ============================================================

  useEffect(() => {
    if (!user) {
      setBadges([]);
      return;
    }

    const loadBadges = async () => {
      try {
        const token = getAuthToken();

        if (!token) {
          setBadges([]);
          return;
        }

        const response = await fetch(
          `${API_BASE_URL}/badges/mine`,
          {
            method: "GET",
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }
        );

        if (!response.ok) {
          console.error(
            "Failed to load fact checker badges:",
            response.status
          );

          setBadges([]);
          return;
        }

        const data = await response.json();

        setBadges(data.badges || []);
      } catch (error) {
        console.error(
          "Failed to load fact checker badges:",
          error
        );

        setBadges([]);
      }
    };

    loadBadges();
  }, [user]);

  return (
    <motion.nav
      initial={{ y: -50, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="bg-white/80 backdrop-blur-md shadow-sm border-b px-4 py-3 sticky top-0 z-50"
    >
      <div className="max-w-4xl mx-auto flex justify-between items-center">

        {/* ======================================================
            LOGO
            ====================================================== */}

        <Link
          href="/"
          className="text-xl font-bold text-indigo-600 flex items-center gap-2 tracking-tight"
        >
          NewsCloud
        </Link>


        {/* ======================================================
            RIGHT SIDE
            ====================================================== */}

        <div className="flex items-center gap-4">

          {/* LEADERBOARD */}

          <Link
            href="/leaderboard"
            className="text-sm text-gray-600 hover:text-blue-600 font-medium"
          >
            Leaderboard
          </Link>


          {user ? (

            <div className="flex items-center gap-4 border-l pl-4">

              {/* ==================================================
                  GEM SCORE
                  ================================================== */}

              <div
                className="
                  flex
                  items-center
                  gap-1
                  text-amber-500
                  font-bold
                  bg-amber-50
                  px-2
                  py-1
                  rounded
                "
                title="GEM score"
              >
                <Gem size={16} />

                <span>
                  {user.gem_score}
                </span>
              </div>


              {/* ==================================================
                  FACT CHECKER BADGE

                  Normally displays only:

                      🏆 3

                  Hover displays the months/years.
                  ================================================== */}

              <FactCheckerBadge
                badges={badges}
              />


              {/* ==================================================
                  USERNAME
                  ================================================== */}

              <div className="flex items-center gap-2 text-sm text-gray-700">

                <UserIcon size={16} />

                <span className="font-medium">
                  {user.username}
                </span>

              </div>


              {/* ==================================================
                  LOGOUT
                  ================================================== */}

              <button
                onClick={logout}
                className="text-gray-500 hover:text-red-500"
                title="Logout"
              >
                <LogOut size={16} />
              </button>

            </div>

          ) : (

            /* ====================================================
               LOGGED OUT
               ==================================================== */

            <div className="flex items-center gap-2 border-l pl-4">

              <Link
                href="/login"
                className="text-sm font-medium text-gray-600 hover:text-blue-600"
              >
                Login
              </Link>

              <Link
                href="/signup"
                className="
                  text-sm
                  font-medium
                  bg-blue-600
                  text-white
                  px-3
                  py-1.5
                  rounded-md
                  hover:bg-blue-700
                "
              >
                Sign Up
              </Link>

            </div>

          )}

        </div>

      </div>
    </motion.nav>
  );
}