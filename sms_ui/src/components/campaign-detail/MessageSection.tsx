import { MessageSquare } from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { Section, Field } from "./Section";
import type { MessageContent, Language } from "@/types/campaign";
import { LANGUAGE_LABELS } from "@/types/campaign";

export function MessageSection({ messageContent }: { messageContent: MessageContent }) {
  const filledLangs = (Object.entries(messageContent.content) as [Language, string][]).filter(
    ([, t]) => t.trim()
  );

  return (
    <Section icon={MessageSquare} title="Message Content">
      <div className="space-y-3">
        <Field label="Default Language" value={LANGUAGE_LABELS[messageContent.default_language]} />
        <Separator />
        {filledLangs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No message content defined.</p>
        ) : (
          filledLangs.map(([lang, text]) => (
            <div key={lang}>
              <span className="text-xs font-medium text-muted-foreground uppercase">
                {LANGUAGE_LABELS[lang]}
                {lang === messageContent.default_language && " (default)"}
              </span>
              <p className="mt-1 text-sm bg-secondary/50 rounded-sm px-3 py-2 whitespace-pre-wrap">
                {text}
              </p>
            </div>
          ))
        )}
      </div>
    </Section>
  );
}
