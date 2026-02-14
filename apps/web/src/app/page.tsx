import { SearchForm } from "@/components/search/search-form";
import { NaturalSearchBar } from "@/components/search/natural-search-bar";
import { Separator } from "@/components/ui/separator";

export default function HomePage() {
  return (
    <div className="flex flex-col items-center">
      {/* Hero */}
      <section className="w-full bg-gradient-to-b from-primary/5 to-background py-16 md:py-24">
        <div className="container mx-auto px-4 text-center">
          <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-3">
            Sky Scanner
          </h1>
          <p className="text-lg text-muted-foreground mb-10">
            Find the best flight deals
          </p>

          <div className="max-w-3xl mx-auto space-y-6">
            <SearchForm />

            <div className="flex items-center gap-4">
              <Separator className="flex-1" />
              <span className="text-xs text-muted-foreground shrink-0">
                or try natural language
              </span>
              <Separator className="flex-1" />
            </div>

            <NaturalSearchBar />
          </div>
        </div>
      </section>
    </div>
  );
}
