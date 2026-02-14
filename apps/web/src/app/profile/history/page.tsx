"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HistoryTable } from "@/components/profile/history-table";
import { useAuthStore } from "@/stores/auth-store";

export default function HistoryPage() {
  const router = useRouter();
  const { accessToken } = useAuthStore();

  useEffect(() => {
    if (!accessToken) {
      router.push("/login");
    }
  }, [accessToken, router]);

  if (!accessToken) return null;

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center gap-4">
        <Link
          href="/profile"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to profile
        </Link>
        <h1 className="text-2xl font-bold">Search History</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Your Searches</CardTitle>
        </CardHeader>
        <CardContent>
          <HistoryTable />
        </CardContent>
      </Card>
    </div>
  );
}
