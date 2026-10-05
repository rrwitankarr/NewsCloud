"use client";

type Badge = {
    badge_number: number;
    award_month: number;
    award_year: number;
    title: string;
};

interface FactCheckerBadgeProps {
    badges: Badge[];
}

const MONTHS = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];

export default function FactCheckerBadge({
    badges,
}: FactCheckerBadgeProps) {

    // --------------------------------------------------------
    // If user has no badges, show nothing.
    // --------------------------------------------------------

    if (!badges || badges.length === 0) {
        return null;
    }


    return (
        <div className="relative group flex items-center">

            {/* =================================================
                NORMAL STATE

                ONLY THIS IS VISIBLE:

                    🏆 3
               ================================================= */}

            <div
                className="
                    flex
                    items-center
                    gap-1
                    px-2
                    py-1
                    rounded-lg
                    cursor-default
                    hover:bg-gray-100
                    transition
                "
            >

                <span className="text-lg">
                    🏆
                </span>

                <span className="font-semibold text-gray-700">
                    {badges.length}
                </span>

            </div>


            {/* =================================================
                HOVER TOOLTIP

                Hidden until user hovers over the badge.
               ================================================= */}

            <div
                className="
                    absolute
                    right-0
                    top-full
                    mt-2
                    w-52
                    rounded-lg
                    bg-gray-900
                    text-white
                    shadow-lg
                    px-4
                    py-3

                    opacity-0
                    invisible

                    group-hover:opacity-100
                    group-hover:visible

                    transition-opacity
                    duration-200

                    z-50
                    pointer-events-none
                "
            >

                <div className="font-semibold text-sm mb-2">
                    Top Fact Checker
                </div>


                <div className="space-y-1">

                    {badges.map((badge) => (

                        <div
                            key={badge.badge_number}
                            className="text-sm text-gray-300"
                        >
                            {MONTHS[badge.award_month]}{" "}
                            {badge.award_year}
                        </div>

                    ))}

                </div>

            </div>

        </div>
    );
}