package lab;

import java.io.StringReader;
import org.eclipse.rdf4j.model.*;
import org.eclipse.rdf4j.rio.*;

/** Feeds the same edge-metadata fact, in RDF-star 2021 and RDF 1.2 syntax, to the rdf4j 4.3.12 parser used by n10s 5.26
 *  and reports how each statement would be treated by n10s' RDFToLPGStatementProcessor (subject-triple → rel property,
 *  object-triple → ignored). */
public class ParserCheck {
    public static void main(String[] a) throws Exception {
        if (a.length > 0) {   // parse a file and count how n10s would map each statement
            Model m = Rio.parse(new java.io.FileReader(a[0]), "", RDFFormat.TURTLESTAR);
            long relProp = 0, ignored = 0, nodeProp = 0, rel = 0;
            for (Statement s : m) {
                if (s.getSubject().isTriple()) relProp++;
                else if (s.getObject().isTriple()) ignored++;
                else if (s.getObject().isLiteral()) nodeProp++;
                else rel++;
            }
            System.out.printf("parsed %d statements: relProps=%d ignored=%d nodeProps=%d rels/types=%d%n", m.size(), relProp, ignored, nodeProp, rel);
            return;
        }
        String p = "@prefix : <http://example.org/fab#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n";
        String[][] cases = {
            {"RDF-star 2021 (Turtle-star)", p + "<< :UPS-1 :feeds :PDU-1 >> :installed 2012 ; :sourceSystem \"BIM\" ."},
            {"RDF 1.2 triple term + reifier", p + ":r1 rdf:reifies <<( :UPS-1 :feeds :PDU-1 )>> ; :installed 2012 ."},
            {"RDF 1.2 annotation syntax", p + ":UPS-1 :feeds :PDU-1 ~ :r1 {| :installed 2012 |} ."},
        };
        for (String[] c : cases) {
            System.out.println("== " + c[0]);
            try {
                Model m = Rio.parse(new StringReader(c[1]), "", RDFFormat.TURTLESTAR);
                for (Statement s : m) {
                    String fate = s.getSubject().isTriple() ? "→ n10s: RELATIONSHIP PROPERTY"
                               : s.getObject().isTriple() ? "→ n10s: IGNORED (triple as object)"
                               : s.getObject().isLiteral() ? "→ n10s: node property" : "→ n10s: relationship";
                    System.out.println("   " + s.getSubject() + " " + s.getPredicate().getLocalName() + " " + s.getObject() + "   " + fate);
                }
            } catch (Exception e) {
                System.out.println("   PARSE FAILED: " + e.getMessage().split("\n")[0]);
            }
        }
    }
}
